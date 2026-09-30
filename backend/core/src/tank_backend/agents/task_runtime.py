"""Single-task execution services for trusted adapters, not an OS sandbox."""

from __future__ import annotations

import asyncio
import json
import math
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar
from uuid import uuid4

from ..plugin.manifest import TASK_RUNTIME_API_VERSION
from ..policy.verdict import AccessLevel, PolicyVerdict
from .subagent import SubAgentCleanupError, SubAgentStopped
from .task_resources import TaskResources, consume_exception

if TYPE_CHECKING:
    from ..llm.profile import LLMProfile
    from ..llm.task_model import TaskModel
    from .base import AgentOutput
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
    category: Literal["execution", "model"] = "execution"
    phase: Literal["prepared", "dispatch", "finished"] = "finished"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    elapsed_ms: float | None = None


class TaskRuntime:
    """Uses the original context for authority and cumulative accounting."""

    api_version = TASK_RUNTIME_API_VERSION

    def __init__(
        self, context: SubAgentContext,
        *, audit: Callable[[ExecutionRecord], Awaitable[None]] | None = None,
        cleanup_timeout: float = 5.0,
    ) -> None:
        self._context = context
        self._model: TaskModel | None = None
        self._task_id: str | None = None
        self._operations: dict[str, object] = {}
        self._records: deque[ExecutionRecord] = deque(maxlen=128)
        self._counts = {"read": 0, "action": 0}
        self._audit = audit
        self._audit_failed = False
        self._audit_lock = asyncio.Lock()
        self._unknown_effect = False
        self._stop_reason: str | None = None
        self._output_bytes = 0
        self._output_events = 0
        self._closed = False
        self._closing: asyncio.Task[None] | None = None
        self._resources = TaskResources(cleanup_timeout / 2)
        self._cleanup_timeout = cleanup_timeout
        self._inflight: set[asyncio.Task[object]] = set()

    @property
    def has_unknown_effect(self) -> bool:
        return self._unknown_effect

    def record_output(self, output: AgentOutput) -> None:
        if self._closed:
            raise SubAgentStopped("runtime_closed")
        if self._stop_reason is not None:
            raise SubAgentStopped(self._stop_reason)
        try:
            encoded = json.dumps({
                "type": output.type.name, "content": output.content,
                "metadata": output.metadata, "target_agent": output.target_agent,
            }, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            self._stop_reason = "invalid_output"
            raise SubAgentStopped("invalid_output") from None
        if (self._output_events >= self._context.max_output_events
                or self._output_bytes + len(encoded) > self._context.max_output_bytes):
            self._stop_reason = "output_limit"
            raise SubAgentStopped("output_limit")
        self._output_events += 1
        self._output_bytes += len(encoded)

    @property
    def task_id(self) -> str:
        if self._task_id is None:
            raise ValueError("task runtime is not bound")
        return self._task_id

    def _policy_verdict(self, tool_name: str, arguments: dict[str, Any]) -> PolicyVerdict:
        from .approval import ToolApprovalPolicy

        policy = self._context.execution_policy or ToolApprovalPolicy()
        permission = {
            "command": "shell", "file": "filesystem", "web": "network", "computer": "desktop",
        }.get(policy.category_for(tool_name))
        if permission is None:
            raise SubAgentStopped("policy_unknown_effect")
        self._context.check(permission)
        return policy.evaluate(tool_name, arguments)

    async def authorize(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Reuse deterministic host policies without a hidden classifier model request."""
        verdict = self._policy_verdict(tool_name, arguments)
        level = verdict.level
        if level == AccessLevel.REQUIRE_APPROVAL:
            resolver = self._context.approval_resolver
            # A host task grant satisfies soft approval; a resolver may narrow it.
            # Hard DENY is never sent to the resolver or overridden by the grant.
            level = (await resolver.resolve(verdict, tool_name, arguments)
                     if resolver is not None else AccessLevel.ALLOW)
        if level != AccessLevel.ALLOW:
            raise SubAgentStopped("policy_denied")
        self._context.check()

    def check_policy_now(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Final synchronous check after an adapter's awaited authorization."""
        if self._policy_verdict(tool_name, arguments).level == AccessLevel.DENY:
            raise SubAgentStopped("policy_denied")

    def restrict_operations(
        self, *, actions: int | None = None, observations: int | None = None,
    ) -> None:
        """Apply host/domain ceilings in native-operation units; never widen an existing ceiling."""
        self.check_open()
        for name, limit in (("max_actions", actions), ("max_observations", observations)):
            if limit is None:
                continue
            if type(limit) is not int or limit < 0:
                raise ValueError("operation limit must be a nonnegative integer")
            current = getattr(self._context, name)
            object.__setattr__(
                self._context, name, min(current, limit) if current is not None else limit,
            )

    def restrict_deadline(self, deadline: float) -> None:
        """Tighten the original task deadline without replacing its runtime or grants."""
        self.check_open()
        if isinstance(deadline, bool) or not math.isfinite(deadline):
            raise ValueError("task deadline must be finite")
        current = self._context.deadline
        object.__setattr__(
            self._context, "deadline", min(current, deadline) if current is not None else deadline,
        )

    @property
    def model(self) -> TaskModel | None:
        return self._model

    def configure_model(
        self, task_id: str, profile: LLMProfile,
        *, input_modalities: frozenset[str] = frozenset({"text"}),
    ) -> None:
        """Host assembly before plugin creation; allocates no HTTP resources."""
        from ..llm.task_model import TaskModel

        self.bind(task_id)
        if self._model is not None:
            raise ValueError("task model is already configured")
        model = TaskModel(task_id, self._context, profile, input_modalities=input_modalities)
        self.own("task-model", model.aclose)
        self._model = model

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
        limit = (self._context.max_observations if operation.kind == "read"
                 else self._context.max_actions)
        if limit is not None and self._counts[operation.kind] >= limit:
            reason = "observation_limit" if operation.kind == "read" else "action_limit"
            raise SubAgentStopped(reason)
        self._counts[operation.kind] += 1
        record = ExecutionRecord(
            self._task_id, uuid4().hex, operation.name, "not_sent", phase="prepared",
        )
        self._records.append(record)
        index = len(self._records) - 1
        await self._emit(record)
        self._check(operation)
        if operation.preflight is not None:
            await operation.preflight(value)
        await self._emit(replace(record, status="unknown", phase="dispatch"))
        self._check(operation)
        self._records[index] = replace(record, status="unknown", phase="dispatch")
        try:
            result = await operation.invoke(value)
        except BaseException:
            if operation.kind == "action":
                self._unknown_effect = True
            raise
        self._records[index] = replace(record, status="returned", phase="finished")
        await self._emit(self._records[index])
        self._check(operation)
        return result

    @property
    def audit_failed(self) -> bool:
        return self._audit_failed

    async def write_audit(self, record: ExecutionRecord) -> None:
        """Commit mandatory evidence, including terminal records during shutdown."""
        if self._audit is None:
            return
        try:
            async with asyncio.timeout(2.0):
                async with self._audit_lock:
                    if self._audit_failed or record.task_id != self._task_id:
                        raise ValueError("invalid task audit state")
                    await self._audit(record)
        except asyncio.CancelledError:
            self._audit_failed = True
            raise
        except Exception:
            self._audit_failed = True
            raise SubAgentStopped("audit_failed") from None

    async def _emit(self, record: ExecutionRecord) -> None:
        await self.write_audit(record)
        self._context.observe("task_execution", **asdict(record))

    def check_open(self) -> None:
        if self._closed:
            raise SubAgentStopped("runtime_closed")
        if self._audit_failed:
            raise SubAgentStopped("audit_failed")
        if self._stop_reason is not None:
            raise SubAgentStopped(self._stop_reason)

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
