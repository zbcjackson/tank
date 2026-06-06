"""WorkerSupervisor — owns the lifecycle of every ``agent`` dispatch.

Phase 2 of the workflow & orchestration roadmap (see
``backend/ORCHESTRATION.md``).

A *worker* is one execution of an agent definition with a starting
prompt. Foreground and background dispatches share this code path —
they differ only in whether the caller awaits the deferred result.

Responsibilities:

- Allocate a ``task_id`` and persist a ``WorkerRunRow`` for every
  dispatch, before the agent ever produces a token.
- Drive ``AgentRunner.run_agent`` to completion, accumulating
  TOKEN content into ``WorkerRun.output``.
- Map terminal outcomes (success / exception / cancel / timeout)
  to ``WorkerStore.finish`` and a single ``BusMessage(type="worker")``
  event.
- Enforce depth / concurrency limits via ``WorkerStore.count_active``
  rather than the in-process ``_AgentTracker`` (so limits survive a
  process restart and apply uniformly across foreground / background).
- Track the in-flight ``asyncio.Task`` for each background dispatch
  so ``stop(task_id)`` can cancel cooperatively.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..pipeline.bus import BusMessage
from .base import AgentOutputType
from .store import WorkerRun, WorkerStore

if TYPE_CHECKING:
    from ..pipeline.bus import Bus
    from .definition import AgentDefinition
    from .runner import AgentRunner

logger = logging.getLogger(__name__)


# Truncate the ``output`` field on bus events so a chatty worker
# doesn't drown the bus or downstream observers. Full text lives in
# the store; observers that need it call ``WorkerStore.get(task_id)``.
_BUS_OUTPUT_MAX_BYTES = 4 * 1024


@dataclass(frozen=True)
class _AskUserResult:
    """Returned by _consume_stream when the sub-agent calls ask_user."""

    question: str
    messages: list[dict[str, Any]]


@dataclass(frozen=True)
class DispatchResult:
    """What ``run_foreground`` returns to the caller."""

    task_id: str
    status: str
    output: str
    error: str | None


class WorkerSupervisorError(Exception):
    """Base for limit / lifecycle errors raised by the supervisor."""


class DepthLimitExceeded(WorkerSupervisorError):
    """Raised when a dispatch would exceed ``max_depth``."""


class ConcurrencyLimitExceeded(WorkerSupervisorError):
    """Raised when a dispatch would exceed ``max_concurrent``."""


class WorkerSupervisor:
    """Lifecycle owner for every agent worker dispatch.

    Inject the ``AgentRunner`` so tests can pass a fake runner that
    yields a fixed sequence of outputs without touching an LLM.
    """

    def __init__(
        self,
        runner: AgentRunner,
        store: WorkerStore,
        *,
        bus: Bus | None = None,
        max_depth: int = 3,
        max_concurrent: int = 5,
    ) -> None:
        self._runner = runner
        self._store = store
        self._bus = bus
        self._max_depth = max_depth
        self._max_concurrent = max_concurrent
        # Tracks in-flight background tasks so ``stop`` can cancel.
        self._tasks: dict[str, asyncio.Task[DispatchResult]] = {}

    @property
    def store(self) -> WorkerStore:
        """Public read-only view of the backing store."""
        return self._store

    # ------------------------------------------------------------------
    # Public API.
    # ------------------------------------------------------------------

    async def run_foreground(
        self,
        *,
        agent_def: AgentDefinition,
        prompt: str,
        description: str = "",
        parent_task_id: str | None = None,
        originating_conversation_id: str | None = None,
        originating_channel: str | None = None,
        parent_msg_id: str | None = None,
        timeout: float | None = None,
    ) -> DispatchResult:
        """Dispatch and await an agent worker.

        On success returns a ``DispatchResult`` with ``status="completed"``.
        On a handled failure returns ``status in {"failed", "cancelled",
        "timeout"}`` rather than raising — the caller (a tool executor)
        wants to feed the failure back to the LLM, not propagate.

        Limit violations DO raise (``DepthLimitExceeded``,
        ``ConcurrencyLimitExceeded``) because they predate any worker
        row being created. The caller surfaces them as tool errors.
        """
        run = self._dispatch(
            agent_def=agent_def, prompt=prompt, description=description,
            parent_task_id=parent_task_id,
            originating_conversation_id=originating_conversation_id,
            originating_channel=originating_channel,
            parent_msg_id=parent_msg_id,
            background=False,
        )
        return await self._drive_to_completion(
            run=run, agent_def=agent_def, timeout=timeout,
        )

    def run_background(
        self,
        *,
        agent_def: AgentDefinition,
        prompt: str,
        description: str = "",
        parent_task_id: str | None = None,
        originating_conversation_id: str | None = None,
        originating_channel: str | None = None,
        parent_msg_id: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Dispatch a worker and return its ``task_id`` immediately.

        The caller does NOT await; the worker runs as an
        ``asyncio.Task`` rooted in the current event loop. Terminal
        delivery happens via ``BusMessage(type="worker")``.

        Returns the ``task_id``. May raise ``DepthLimitExceeded`` /
        ``ConcurrencyLimitExceeded`` synchronously.
        """
        run = self._dispatch(
            agent_def=agent_def, prompt=prompt, description=description,
            parent_task_id=parent_task_id,
            originating_conversation_id=originating_conversation_id,
            originating_channel=originating_channel,
            parent_msg_id=parent_msg_id,
            background=True,
        )
        task = asyncio.create_task(
            self._drive_to_completion(
                run=run, agent_def=agent_def, timeout=timeout,
            ),
            name=f"worker:{run.task_id}",
        )
        self._tasks[run.task_id] = task
        task.add_done_callback(
            lambda _t, tid=run.task_id: self._tasks.pop(tid, None),
        )
        return run.task_id

    def stop(self, task_id: str) -> bool:
        """Cancel an in-flight worker by task_id.

        Returns True if a running task was found and cancellation
        was requested. Returns False if the task is unknown or already
        terminal. Cancellation is cooperative — the worker's eventual
        terminal state is recorded by ``_drive_to_completion``.
        """
        task = self._tasks.get(task_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def wait(self, task_id: str, timeout: float | None = None) -> WorkerRun | None:
        """Block until the run with ``task_id`` reaches a terminal status.

        Returns the final ``WorkerRun`` (or ``None`` if not found). If
        ``timeout`` elapses first, returns the current row regardless.
        """
        existing = self._store.get(task_id)
        if existing is None:
            return None
        if existing.status != "running":
            return existing
        task = self._tasks.get(task_id)
        if task is None:
            # No in-process task — supervisor was restarted; fall back
            # to a poll loop bounded by ``timeout``.
            return await self._poll_until_terminal(task_id, timeout=timeout)
        with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return self._store.get(task_id)

    async def _poll_until_terminal(
        self, task_id: str, *, timeout: float | None,
    ) -> WorkerRun | None:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            run = self._store.get(task_id)
            if run is None or run.status != "running":
                return run
            if deadline is not None and time.monotonic() >= deadline:
                return run
            await asyncio.sleep(0.1)

    # ------------------------------------------------------------------
    # Shared dispatch path — limits + create row + bus event.
    # ------------------------------------------------------------------

    def _dispatch(
        self,
        *,
        agent_def: AgentDefinition,
        prompt: str,
        description: str,
        parent_task_id: str | None,
        originating_conversation_id: str | None,
        originating_channel: str | None,
        parent_msg_id: str | None,
        background: bool,
    ) -> WorkerRun:
        self._enforce_limits(parent_task_id=parent_task_id)
        task_id = self._new_task_id()
        run = self._store.create(
            task_id=task_id,
            agent_def=agent_def.name,
            prompt=prompt,
            description=description,
            parent_task_id=parent_task_id,
            originating_conversation_id=originating_conversation_id,
            originating_channel=originating_channel,
            parent_msg_id=parent_msg_id,
            background=background,
        )
        self._post_bus_event("started", run)
        return run

    # ------------------------------------------------------------------
    # Internal — drive the AgentRunner stream.
    # ------------------------------------------------------------------

    async def _drive_to_completion(
        self,
        *,
        run: WorkerRun,
        agent_def: AgentDefinition,
        timeout: float | None,
        initial_messages: list[dict[str, Any]] | None = None,
    ) -> DispatchResult:
        start = time.monotonic()
        output_chunks: list[str] = []
        messages: list[dict[str, Any]] = (
            initial_messages or [{"role": "user", "content": run.prompt}]
        )

        try:
            ask_user = await asyncio.wait_for(
                self._consume_stream(
                    agent_def=agent_def,
                    run=run,
                    output_chunks=output_chunks,
                    initial_messages=initial_messages,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            error = f"Worker timed out after {elapsed:.1f}s"
            return self._finalize(
                run=run, status="timeout", output="".join(output_chunks),
                error=error, messages=messages,
            )
        except asyncio.CancelledError:
            error = "Worker cancelled"
            self._finalize(
                run=run, status="cancelled", output="".join(output_chunks),
                error=error, messages=messages,
            )
            raise
        except Exception as e:  # noqa: BLE001 — failure is the result we return
            logger.exception(
                "Worker '%s' (task=%s) failed",
                agent_def.name, run.task_id,
            )
            return self._finalize(
                run=run, status="failed", output="".join(output_chunks),
                error=f"{type(e).__name__}: {e}", messages=messages,
            )

        if ask_user is not None:
            self._store.pause(
                run.task_id,
                output="".join(output_chunks),
                question=ask_user.question,
                messages=ask_user.messages,
            )
            self._post_bus_event("waiting", run, question=ask_user.question)
            return DispatchResult(
                task_id=run.task_id, status="waiting",
                output="".join(output_chunks), error=None,
            )

        return self._finalize(
            run=run, status="completed", output="".join(output_chunks),
            error=None, messages=messages,
        )

    async def _consume_stream(
        self,
        *,
        agent_def: AgentDefinition,
        run: WorkerRun,
        output_chunks: list[str],
        initial_messages: list[dict[str, Any]] | None = None,
    ) -> _AskUserResult | None:
        """Drain ``runner.run_agent`` into ``output_chunks``.

        Returns an ``_AskUserResult`` if the sub-agent called ask_user,
        or ``None`` for a normal completion.
        """
        messages = initial_messages or [{"role": "user", "content": run.prompt}]
        ask_user_question: str | None = None
        async for event in self._runner.run_agent(
            agent_def=agent_def,
            messages=messages,
            parent_agent_id=run.parent_task_id,
            background=False,
        ):
            if event.type == AgentOutputType.TOKEN:
                output_chunks.append(event.content)
            elif (
                event.type == AgentOutputType.TOOL_RESULT
                and event.metadata.get("name") == "ask_user"
                and event.metadata.get("status") == "success"
            ):
                ask_user_question = event.content
            elif (
                event.type == AgentOutputType.DONE
                and ask_user_question is not None
            ):
                turn_messages = event.metadata.get("turn_messages", [])
                return _AskUserResult(
                    question=ask_user_question,
                    messages=messages + turn_messages,
                )
        return None

    def _finalize(
        self,
        *,
        run: WorkerRun,
        status: str,
        output: str,
        error: str | None,
        messages: list[dict[str, Any]],
    ) -> DispatchResult:
        # Round-trip messages so a future ``task_id`` resume can pick
        # up the prompt; the assistant turn lives only in ``output``
        # for now and is appended on next dispatch.
        self._store.finish(
            run.task_id,
            status=status,  # type: ignore[arg-type]
            output=output,
            error=error,
            messages=messages,
        )
        result = DispatchResult(
            task_id=run.task_id,
            status=status,
            output=output,
            error=error,
        )
        self._post_bus_event(_terminal_event_name(status), run, result=result)
        return result

    # ------------------------------------------------------------------
    # Limits.
    # ------------------------------------------------------------------

    def _enforce_limits(self, *, parent_task_id: str | None) -> None:
        depth = self._depth_of(parent_task_id)
        if depth >= self._max_depth:
            raise DepthLimitExceeded(
                f"max depth {self._max_depth} reached at depth {depth}",
            )
        active = self._store.count_active()
        if active >= self._max_concurrent:
            raise ConcurrencyLimitExceeded(
                f"max concurrent workers ({self._max_concurrent}) reached "
                f"({active} active)",
            )

    def _depth_of(self, parent_task_id: str | None) -> int:
        """Compute depth by walking parent_task_id back to a root."""
        if parent_task_id is None:
            return 0
        depth = 0
        cursor = parent_task_id
        while cursor is not None and depth < self._max_depth + 1:
            row = self._store.get(cursor)
            if row is None:
                # Parent not in store — treat as depth-1 (leaf parent).
                return depth + 1
            depth += 1
            cursor = row.parent_task_id
        return depth

    # ------------------------------------------------------------------
    # Bus.
    # ------------------------------------------------------------------

    def _post_bus_event(
        self,
        event: str,
        run: WorkerRun,
        *,
        result: DispatchResult | None = None,
        question: str | None = None,
    ) -> None:
        if self._bus is None:
            return
        payload: dict[str, Any] = {
            "event": event,
            "task_id": run.task_id,
            "agent_def": run.agent_def,
            "description": run.description,
            "originating_conversation_id": run.originating_conversation_id,
            "originating_channel": run.originating_channel,
            "parent_msg_id": run.parent_msg_id,
        }
        if result is not None:
            payload["status"] = result.status
            payload["output"] = _truncate(result.output, _BUS_OUTPUT_MAX_BYTES)
            if result.error is not None:
                payload["error"] = result.error
        if question is not None:
            payload["question"] = question
        self._bus.post(BusMessage(
            type="worker",
            source="worker_supervisor",
            payload=payload,
        ))

    # ------------------------------------------------------------------
    # Resume a waiting worker.
    # ------------------------------------------------------------------

    async def resume_with_answer(self, task_id: str, answer: str) -> bool:
        """Resume a waiting worker with the user's answer.

        Appends the answer to the persisted message history, transitions
        back to running, and re-dispatches in the background.
        """
        run = self._store.get(task_id)
        if run is None or run.status != "waiting":
            return False

        messages = list(run.messages)
        messages.append({"role": "user", "content": answer})

        self._store.resume(task_id)

        agent_def = self._runner.get_definition(run.agent_def)
        if agent_def is None:
            self._store.finish(
                task_id, status="failed",
                error=f"agent definition '{run.agent_def}' not found on resume",
            )
            return False

        self._post_bus_event("started", run)

        task = asyncio.create_task(
            self._drive_to_completion(
                run=run, agent_def=agent_def, timeout=None,
                initial_messages=messages,
            ),
            name=f"worker:{task_id}:resumed",
        )
        self._tasks[task_id] = task
        task.add_done_callback(
            lambda _t, tid=task_id: self._tasks.pop(tid, None),
        )
        return True

    # ------------------------------------------------------------------
    # Helpers.
    # ------------------------------------------------------------------

    @staticmethod
    def _new_task_id() -> str:
        return f"t_{uuid.uuid4().hex[:12]}"


def _terminal_event_name(status: str) -> str:
    """Map terminal status → bus event name."""
    return {
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
        "timeout": "timeout",
    }.get(status, "completed")


def _truncate(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # Decode-safe truncate.
    return encoded[: max_bytes - 1].decode("utf-8", errors="ignore") + "…"
