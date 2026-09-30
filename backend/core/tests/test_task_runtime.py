"""Task services exercise real governance with fake external operations."""

import asyncio
import time

import pytest

from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentContext,
    SubAgentStopped,
)


async def test_registered_operation_rechecks_authority_after_preflight() -> None:
    from tank_backend.agents.task_runtime import TaskOperation

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
    )
    runtime = context.runtime
    runtime.bind("task")
    sent: list[str] = []

    async def preflight(value: str) -> None:
        await asyncio.sleep(0)
        context.authorization.revoke()

    async def write(value: str) -> str:
        sent.append(value)
        return value

    operation = TaskOperation("write", frozenset({"filesystem"}), "action", write, preflight)
    runtime.register(operation)
    with pytest.raises(SubAgentStopped, match="authorization"):
        await runtime.execute(operation, "document")
    assert sent == []
    assert runtime.records[-1].status == "not_sent"


async def test_operation_allowlist_limits_and_task_binding() -> None:
    from tank_backend.agents.task_runtime import TaskOperation

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
        max_actions=1,
    )
    runtime = context.runtime
    runtime.bind("task")
    calls: list[str] = []

    async def write(value: str) -> str:
        calls.append(value)
        return "written"

    operation = TaskOperation("write", frozenset({"filesystem"}), "action", write)
    forged = TaskOperation("write", frozenset(), "action", write)
    runtime.register(operation)
    with pytest.raises(SubAgentStopped, match="unregistered"):
        await runtime.execute(forged, "forged")
    assert await runtime.execute(operation, "document") == "written"
    with pytest.raises(SubAgentStopped, match="action_limit"):
        await runtime.execute(operation, "twice")
    with pytest.raises(ValueError, match="different task"):
        runtime.bind("another")
    assert calls == ["document"]
    assert len(runtime.records) == 1


@pytest.mark.parametrize("fail_status", ["unknown", "returned"])
async def test_required_audit_failure_latches_before_further_dispatch(fail_status: str) -> None:
    from tank_backend.agents.task_runtime import ExecutionRecord, TaskOperation

    calls: list[str] = []

    async def audit(record: ExecutionRecord) -> None:
        if record.status == fail_status:
            raise OSError("private audit path must not leak")

    async def write(value: str) -> str:
        calls.append(value)
        return value

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
        audit=audit,
    )
    runtime = context.runtime
    runtime.bind("task")
    operation = TaskOperation("write", frozenset({"filesystem"}), "action", write)
    runtime.register(operation)
    with pytest.raises(SubAgentStopped, match="audit_failed"):
        await runtime.execute(operation, "document")
    with pytest.raises(SubAgentStopped, match="audit_failed"):
        await runtime.execute(operation, "again")
    assert calls == ([] if fail_status == "unknown" else ["document"])
    assert runtime.records[-1].status == ("not_sent" if fail_status == "unknown" else "returned")
    with pytest.raises(SubAgentStopped, match="audit_failed"):
        context.check("filesystem")


async def test_cleanup_attempts_all_resources_and_closes_business_gate() -> None:
    from tank_backend.agents.subagent import SubAgentCleanupError

    context = SubAgentContext(SubAgentAuthorization(), SubAgentBudget(), asyncio.Event())
    runtime = context.runtime
    runtime.bind("task")
    closed: list[str] = []

    async def close_first() -> None:
        closed.append("first")

    async def close_second() -> None:
        closed.append("second")
        with pytest.raises(SubAgentStopped, match="runtime_closed"):
            context.check()
        raise OSError("cleanup failed")

    runtime.own("first", close_first)
    runtime.own("second", close_second)
    context.authorization.revoke()
    context.cancel.set()
    for _ in range(2):
        with pytest.raises(SubAgentCleanupError):
            await runtime.aclose()
    assert closed == ["second", "first"]


async def test_hung_cleanup_is_bounded_and_other_resources_are_released() -> None:
    from tank_backend.agents.subagent import SubAgentCleanupError
    from tank_backend.agents.task_runtime import TaskRuntime

    context = SubAgentContext(SubAgentAuthorization(), SubAgentBudget(), asyncio.Event())
    runtime = TaskRuntime(context, cleanup_timeout=0.02)
    released = asyncio.Event()
    cancelled = asyncio.Event()

    async def good() -> None:
        released.set()

    async def hung() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    runtime.own("good", good)
    runtime.own("hung", hung)
    with pytest.raises(SubAgentCleanupError):
        await asyncio.wait_for(runtime.aclose(), 1)
    assert released.is_set() and cancelled.is_set()


async def test_cancel_inflight_keeps_unknown_and_cleanup_joins_operation() -> None:
    from tank_backend.agents.task_runtime import TaskOperation

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
    )
    runtime = context.runtime
    runtime.bind("task")
    entered, ended = asyncio.Event(), asyncio.Event()

    async def write(value: str) -> str:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            ended.set()
        return value

    operation = TaskOperation("write", frozenset({"filesystem"}), "action", write)
    runtime.register(operation)
    pending = asyncio.create_task(runtime.execute(operation, "document"))
    await entered.wait()
    context.cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pending, 0.5)
    await runtime.aclose()
    assert ended.is_set()
    assert runtime.records[-1].status == "unknown"


async def test_ordinary_observer_failure_does_not_change_execution() -> None:
    from tank_backend.agents.task_runtime import TaskOperation

    class BrokenObserver:
        def on_event(self, kind: str, metadata: dict[str, object]) -> None:
            raise OSError("telemetry unavailable")

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
        observer=BrokenObserver(),
    )
    runtime = context.runtime
    runtime.bind("task")

    async def read(value: str) -> str:
        return value

    operation = TaskOperation("read", frozenset({"filesystem"}), "read", read)
    runtime.register(operation)
    assert await runtime.execute(operation, "document") == "document"


async def test_unknown_action_is_not_replayed_but_readback_is_allowed() -> None:
    from tank_backend.agents.task_runtime import TaskOperation

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
    )
    runtime = context.runtime
    runtime.bind("task")
    sent: list[str] = []

    async def write(value: str) -> str:
        sent.append(value)
        raise OSError("response lost")

    async def read(value: str) -> str:
        return "exists"

    action = TaskOperation("write", frozenset({"filesystem"}), "action", write)
    observation = TaskOperation("read", frozenset({"filesystem"}), "read", read)
    runtime.register(action)
    runtime.register(observation)
    with pytest.raises(OSError):
        await runtime.execute(action, "document")
    assert await runtime.execute(observation, "document") == "exists"
    with pytest.raises(SubAgentStopped, match="effect_unknown"):
        await runtime.execute(action, "document")
    assert sent == ["document"]


@pytest.mark.parametrize("stop", ["cancel", "deadline", "permission", "parameters"])
async def test_preflight_stop_does_not_dispatch(stop: str) -> None:
    from tank_backend.agents.task_runtime import TaskOperation

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
        deadline=time.monotonic() - 1 if stop == "deadline" else None,
    )
    runtime = context.runtime
    runtime.bind("task")
    sent: list[int] = []

    async def preflight(value: int) -> None:
        if stop == "cancel":
            context.cancel.set()
        if value < 0:
            raise ValueError("invalid range")

    async def write(value: int) -> int:
        sent.append(value)
        return value

    operation = TaskOperation(
        "write", frozenset({"network" if stop == "permission" else "filesystem"}),
        "action", write, preflight,
    )
    runtime.register(operation)
    exception = {
        "cancel": asyncio.CancelledError, "deadline": TimeoutError,
        "permission": SubAgentStopped, "parameters": ValueError,
    }[stop]
    with pytest.raises(exception):
        await runtime.execute(operation, -1 if stop == "parameters" else 1)
    await runtime.aclose()
    assert sent == []
    assert all(record.status == "not_sent" for record in runtime.records)


async def test_read_quota_is_shared_and_bounded() -> None:
    from tank_backend.agents.task_runtime import TaskOperation

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
    )
    runtime = context.runtime
    runtime.bind("task")
    reads: list[int] = []

    async def read(value: int) -> int:
        reads.append(value)
        return value

    first = TaskOperation("first", frozenset({"filesystem"}), "read", read)
    second = TaskOperation("second", frozenset({"filesystem"}), "read", read)
    runtime.register(first)
    runtime.register(second)
    runtime.restrict_operations(observations=64)
    for index in range(64):
        await runtime.execute(first if index % 2 else second, index)
    with pytest.raises(SubAgentStopped, match="observation_limit"):
        await runtime.execute(second, 65)
    assert len(reads) == len(runtime.records) == 64


async def test_repeated_close_cancellation_does_not_cancel_release() -> None:
    context = SubAgentContext(SubAgentAuthorization(), SubAgentBudget(), asyncio.Event())
    runtime = context.runtime
    started, finish = asyncio.Event(), asyncio.Event()
    releases: list[str] = []

    async def detach() -> None:
        started.set()
        await finish.wait()
        releases.append("detached")

    runtime.own("borrowed_page_lease", detach)
    first = asyncio.create_task(runtime.aclose())
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(runtime.aclose())
    await asyncio.sleep(0)
    second.cancel()
    with pytest.raises(asyncio.CancelledError):
        await second
    finish.set()
    await runtime.aclose()
    assert releases == ["detached"]


async def test_cancelled_required_audit_stops_later_business_calls() -> None:
    from tank_backend.agents.task_runtime import ExecutionRecord, TaskOperation

    entered = asyncio.Event()

    async def audit(record: ExecutionRecord) -> None:
        entered.set()
        await asyncio.Event().wait()

    async def read(value: str) -> str:
        return value

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
        audit=audit,
    )
    runtime = context.runtime
    runtime.bind("task")
    operation = TaskOperation("read", frozenset({"filesystem"}), "read", read)
    runtime.register(operation)
    pending = asyncio.create_task(runtime.execute(operation, "document"))
    await entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    with pytest.raises(SubAgentStopped, match="audit_failed"):
        context.check()
    await runtime.aclose()



def test_deadline_restriction_never_extends_or_replaces_runtime():
    context = SubAgentContext(SubAgentAuthorization(), SubAgentBudget(), asyncio.Event())
    runtime = context.runtime
    runtime.restrict_deadline(100)
    runtime.restrict_deadline(200)
    assert context.deadline == 100
    runtime.restrict_deadline(50)
    assert context.deadline == 50 and context.runtime is runtime
    with pytest.raises(ValueError, match="finite"):
        runtime.restrict_deadline(float("nan"))


async def test_native_policy_uses_the_existing_file_policy_without_overriding_denial(tmp_path):
    from tank_backend.agents.approval import ToolApprovalPolicy
    from tank_backend.config.models import FileAccessConfig
    from tank_backend.policy.file_access import FileAccessPolicy
    from tank_backend.policy.verdict import AccessLevel, AlwaysApproveResolver

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"filesystem"})), SubAgentBudget(), asyncio.Event(),
        execution_policy=ToolApprovalPolicy(file_policy=FileAccessPolicy(
            FileAccessConfig(default_write=AccessLevel.DENY),
        )),
        approval_resolver=AlwaysApproveResolver(),
    )
    with pytest.raises(SubAgentStopped, match="policy_denied"):
        await context.runtime.authorize("file_write", {"path": str(tmp_path / "file")})
