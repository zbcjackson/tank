"""Tools for inspecting and controlling worker dispatches.

Phase 2 step 4 of the workflow & orchestration roadmap (see
``backend/ORCHESTRATION.md``).

Three tools, all read- or control-side companions to ``agent``:

- ``agent_status`` — inspect a single worker by ``task_id``.
- ``agent_stop``   — request cancellation of an in-flight worker.
- ``list_active_agents`` — enumerate workers currently in ``status=running``.

All three return ``ToolResult`` with a JSON-encoded ``content`` and a
short ``display`` summary, matching the rest of the tool surface.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..tools.base import BaseTool, ToolInfo, ToolParameter, ToolResult
from .store import WorkerRun, WorkerStore
from .supervisor import WorkerSupervisor

logger = logging.getLogger(__name__)


def _run_to_dict(run: WorkerRun, *, include_output: bool = True) -> dict[str, Any]:
    """Public-facing JSON shape for a worker run.

    Excludes ``messages`` (large) and ``prompt`` (already known to the
    caller). ``output`` is included by default but caller can elide
    it when listing many workers.
    """
    data: dict[str, Any] = {
        "task_id": run.task_id,
        "agent_def": run.agent_def,
        "description": run.description,
        "status": run.status,
        "background": run.background,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "originating_conversation_id": run.originating_conversation_id,
        "originating_channel": run.originating_channel,
    }
    if include_output:
        data["output"] = run.output
        data["error"] = run.error
    return data


class AgentStatusTool(BaseTool):
    """Inspect a worker dispatch by ``task_id``.

    Optional ``wait=True`` blocks (up to ``timeout_ms``) until the run
    reaches a terminal status. The wait is cooperative — the LLM is
    free to call other tools instead of blocking, but ``wait=True`` is
    convenient for "kick off → check back" patterns.
    """

    def __init__(self, store: WorkerStore, supervisor: WorkerSupervisor) -> None:
        self._store = store
        self._supervisor = supervisor

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="agent_status",
            description=(
                "Get the status and output of a worker dispatched via "
                "the agent tool. Pass wait=true to block until the run "
                "reaches a terminal status."
            ),
            parameters=[
                ToolParameter(
                    name="task_id",
                    type="string",
                    description="The task_id returned by a prior agent(...) call.",
                    required=True,
                ),
                ToolParameter(
                    name="wait",
                    type="boolean",
                    description=(
                        "Block until the run is no longer 'running'. "
                        "Defaults to false."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="timeout_ms",
                    type="integer",
                    description=(
                        "Max wait time when wait=true, in milliseconds. "
                        "Default 60000 (60s)."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        task_id = kwargs["task_id"]
        wait = bool(kwargs.get("wait", False))
        timeout_ms = int(kwargs.get("timeout_ms", 60000))

        if wait:
            run = await self._supervisor.wait(
                task_id, timeout=max(timeout_ms, 0) / 1000.0,
            )
        else:
            run = self._store.get(task_id)

        if run is None:
            return ToolResult(
                content=json.dumps(
                    {"error": f"task_id '{task_id}' not found"},
                    ensure_ascii=False,
                ),
                display=f"Task {task_id} not found.",
                error=True,
            )

        payload = _run_to_dict(run)
        return ToolResult(
            content=json.dumps(payload, ensure_ascii=False),
            display=f"Task {task_id}: {run.status}",
        )


class AgentStopTool(BaseTool):
    """Cancel an in-flight worker.

    Idempotent: stopping an already-terminal worker is not an error,
    just a no-op. The LLM can use ``agent_status`` to confirm the
    eventual terminal state.
    """

    def __init__(self, store: WorkerStore, supervisor: WorkerSupervisor) -> None:
        self._store = store
        self._supervisor = supervisor

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="agent_stop",
            description=(
                "Cancel a worker dispatch. The worker transitions to "
                "status='cancelled' once the cancellation is observed. "
                "Idempotent — safe to call on already-finished workers."
            ),
            parameters=[
                ToolParameter(
                    name="task_id",
                    type="string",
                    description="The task_id to cancel.",
                    required=True,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        task_id = kwargs["task_id"]
        existing = self._store.get(task_id)
        if existing is None:
            return ToolResult(
                content=json.dumps(
                    {"error": f"task_id '{task_id}' not found"},
                    ensure_ascii=False,
                ),
                display=f"Task {task_id} not found.",
                error=True,
            )
        if existing.status != "running":
            return ToolResult(
                content=json.dumps(
                    {
                        "task_id": task_id,
                        "status": existing.status,
                        "note": "already terminal",
                    },
                    ensure_ascii=False,
                ),
                display=f"Task {task_id} already {existing.status}; nothing to stop.",
            )
        cancelled = self._supervisor.stop(task_id)
        if not cancelled:
            return ToolResult(
                content=json.dumps(
                    {
                        "task_id": task_id,
                        "status": "running",
                        "note": (
                            "no in-process task; worker may be running on "
                            "another process or already winding down"
                        ),
                    },
                    ensure_ascii=False,
                ),
                display=f"Task {task_id} could not be stopped from this process.",
            )
        return ToolResult(
            content=json.dumps(
                {"task_id": task_id, "status": "cancelling"},
                ensure_ascii=False,
            ),
            display=f"Cancellation requested for task {task_id}.",
        )


class ListActiveAgentsTool(BaseTool):
    """List worker dispatches that are currently running."""

    def __init__(self, store: WorkerStore) -> None:
        self._store = store

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="list_active_agents",
            description=(
                "List worker dispatches currently running. Returns "
                "task_id, agent_def, description, started_at for each."
            ),
            parameters=[],
        )

    async def execute(self, **_kwargs: Any) -> ToolResult:
        runs = self._store.list_active()
        items = [_run_to_dict(r, include_output=False) for r in runs]
        if not items:
            return ToolResult(
                content=json.dumps({"workers": []}, ensure_ascii=False),
                display="No active workers.",
            )
        return ToolResult(
            content=json.dumps({"workers": items}, ensure_ascii=False),
            display=f"{len(items)} active worker(s).",
        )
