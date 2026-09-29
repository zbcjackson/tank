"""Single-task execution services for trusted adapters, not an OS sandbox."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Generic, Literal, TypeVar
from uuid import uuid4

from .subagent import SubAgentCleanupError, SubAgentStopped
from .task_resources import TaskResources, consume_exception

if TYPE_CHECKING:
    from .subagent import SubAgentContext

Input = TypeVar("Input")
Output = TypeVar("Output")


@dataclass(frozen=True, eq=False)
class TaskOperation(Generic[Input, Output]):
    """Host adapter registration; permissions never come from model arguments.

    Preflight validates domain parameters and native references. Adapters that
    await again inside invoke must check the context at their final native boundary.
    """

    name: str
    permissions: frozenset[str]
    kind: Literal["read", "action"]
    invoke: Callable[[Input], Awaitable[Output]]
    preflight: Callable[[Input], Awaitable[None]] | None = None


@dataclass(frozen=True)
class ExecutionRecord:
    task_id: str
    call_id: str
    operation: str
    status: Literal["not_sent", "unknown", "returned"]


class TaskRuntime:
    """Uses the original context for authority and cumulative accounting."""

    def __init__(
        self, context: SubAgentContext,
        *, audit: Callable[[ExecutionRecord], Awaitable[None]] | None = None,
        cleanup_timeout: float = 5.0,
    ) -> None:
        self._context = context
        self._task_id: str | None = None
        self._operations: dict[str, object] = {}
        self._records: list[ExecutionRecord] = []
        self._counts = {"read": 0, "action": 0}
        self._audit = audit
        self._audit_failed = False
        self._unknown_effect = False
        self._closed = False
        self._closing: asyncio.Task[None] | None = None
        self._resources = TaskResources(cleanup_timeout / 2)
        self._cleanup_timeout = cleanup_timeout
        self._inflight: set[asyncio.Task[object]] = set()

    @property
    def records(self) -> tuple[ExecutionRecord, ...]:
        return tuple(self._records)

    def bind(self, task_id: str) -> None:
        self.check_open()
        if not task_id or self._task_id not in (None, task_id):
            raise ValueError("runtime belongs to a different task")
        self._task_id = task_id

    def register(self, operation: TaskOperation[Input, Output]) -> None:
        self.check_open()
        if (
            not operation.name or len(operation.name) > 128
            or operation.kind not in self._counts or not operation.permissions
            or len(self._operations) >= 32
        ):
            raise ValueError("invalid operation registration")
        if operation.name in self._operations or self._records:
            raise ValueError("operations must be uniquely registered before execution")
        self._operations[operation.name] = operation

    def _check(self, operation: TaskOperation[Input, Output]) -> None:
        self.check_open()
        self._context.check()
        for permission in operation.permissions:
            self._context.check(permission)

    async def execute(self, operation: TaskOperation[Input, Output], value: Input) -> Output:
        self.check_open()
        if self._inflight:
            raise SubAgentStopped("operation_inflight")
        task = asyncio.create_task(self._execute(operation, value))
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)
        task.add_done_callback(consume_exception)
        cancelled = asyncio.create_task(self._context.cancel.wait())
        try:
            async with asyncio.timeout_at(self._context.deadline):
                done, _ = await asyncio.wait({task, cancelled}, return_when=asyncio.FIRST_COMPLETED)
                if task not in done:
                    raise asyncio.CancelledError("task cancelled during operation")
                return task.result()
        finally:
            cancelled.cancel()
            if not task.done() and not task.cancelling():
                task.cancel()
            await asyncio.gather(cancelled, return_exceptions=True)

    async def _execute(self, operation: TaskOperation[Input, Output], value: Input) -> Output:
        if self._task_id is None or self._operations.get(operation.name) is not operation:
            raise SubAgentStopped("operation_unregistered")
        self._check(operation)
        if operation.kind == "action" and self._unknown_effect:
            raise SubAgentStopped("effect_unknown")
        limit = 64 if operation.kind == "read" else min(
            32, self._context.max_steps if self._context.max_steps is not None else 32,
        )
        if self._counts[operation.kind] >= limit:
            reason = "observation_limit" if operation.kind == "read" else "action_limit"
            raise SubAgentStopped(reason)
        self._counts[operation.kind] += 1
        index = len(self._records)
        record = ExecutionRecord(self._task_id, uuid4().hex, operation.name, "not_sent")
        self._records.append(record)
        await self._emit(record)
        self._check(operation)
        if operation.preflight is not None:
            await operation.preflight(value)
        await self._emit(replace(record, status="unknown"))
        self._check(operation)
        self._records[index] = replace(record, status="unknown")
        try:
            result = await operation.invoke(value)
        except BaseException:
            if operation.kind == "action":
                self._unknown_effect = True
            raise
        self._records[index] = replace(record, status="returned")
        await self._emit(self._records[index])
        self._check(operation)
        return result

    async def _emit(self, record: ExecutionRecord) -> None:
        if self._audit is not None:
            try:
                await self._audit(record)
            except asyncio.CancelledError:
                self._audit_failed = True
                raise
            except Exception as exc:
                self._audit_failed = True
                raise SubAgentStopped("audit_failed") from exc
        self._context.observe("task_execution", **asdict(record))

    def check_open(self) -> None:
        if self._closed:
            raise SubAgentStopped("runtime_closed")
        if self._audit_failed:
            raise SubAgentStopped("audit_failed")

    def own(self, name: str, release: Callable[[], Awaitable[None]]) -> None:
        """Register task-owned cleanup (or detach only for a borrowed resource).

        Shared host clients must not be registered here. Registration is synchronous
        so an adapter can transfer ownership immediately after creation, even if
        authorization was revoked while creation was in flight.
        """
        self.check_open()
        self._resources.own(name, release)

    def begin_close(self) -> None:
        self._closed = True

    async def aclose(self) -> None:
        if self._closing is None:
            self.begin_close()
            self._closing = asyncio.create_task(self._close())
            self._closing.add_done_callback(consume_exception)
        await asyncio.shield(self._closing)

    async def _close(self) -> None:
        failures: list[str] = []
        timeout = self._cleanup_timeout / 2
        inflight = tuple(self._inflight)
        for task in inflight:
            if not task.cancelling():
                task.cancel()
        if inflight:
            _, pending = await asyncio.wait(inflight, timeout=timeout)
            if pending:
                failures.append("inflight")
        try:
            await self._resources.aclose()
        except SubAgentCleanupError as exc:
            failures.append(str(exc))
        if failures:
            raise SubAgentCleanupError("Task resource cleanup unconfirmed: " + ", ".join(failures))
