"""Integration tests for the unified approval flow.

These tests cover the integration seams that unit tests missed:
1. ApprovalGateExecutor handles file/network tools (not just commands)
2. AlwaysApproveResolver / AlwaysDenyResolver work for file tools
3. ToolApprovalPolicy routes to correct policy per tool type
4. Job CRUD syncs schedules to APScheduler
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.agents.approval import (
    ApprovalGateExecutor,
    InteractiveResolver,
    PendingToolCallStore,
    ToolApprovalPolicy,
)
from tank_backend.core.events import UpdateType
from tank_backend.pipeline.bus import Bus
from tank_backend.policy.file_access import FileAccessPolicy, FileAccessRule
from tank_backend.policy.network_access import (
    NetworkAccessPolicy,
    NetworkAccessRule,
)
from tank_backend.policy.verdict import (
    AccessLevel,
    AlwaysApproveResolver,
    AlwaysDenyResolver,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_call(name: str, args: dict) -> MagicMock:
    tc = MagicMock()
    tc.id = "call_test"
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _make_gate(
    policy: ToolApprovalPolicy,
    resolver=None,
    tool_manager=None,
) -> tuple[ApprovalGateExecutor, PendingToolCallStore, Bus]:
    store = PendingToolCallStore()
    bus = Bus()
    tm = tool_manager or MagicMock()
    if tool_manager is None:
        tm.execute_openai_tool_call = AsyncMock(
            return_value={"ok": True},
        )

    if resolver is None:
        resolver = InteractiveResolver(
            pending_store=store, session_id="s1", bus=bus,
            current_msg_id_fn=lambda: "msg1",
        )

    gate = ApprovalGateExecutor(
        tool_manager=tm,
        approval_policy=policy,
        resolver=resolver,
        pending_store=store,
        session_id="s1",
        bus=bus,
        current_msg_id_fn=lambda: "msg1",
    )
    return gate, store, bus


# ---------------------------------------------------------------------------
# 1. Gate handles file tools through ToolApprovalPolicy
# ---------------------------------------------------------------------------


class TestGateFileToolIntegration:
    """file_write with REQUIRE_APPROVAL goes through the gate."""

    def _policy(
        self, default_write: AccessLevel = AccessLevel.REQUIRE_APPROVAL,
    ) -> ToolApprovalPolicy:
        fp = FileAccessPolicy(
            default_write=default_write,
            default_read=AccessLevel.ALLOW,
        )
        return ToolApprovalPolicy(file_policy=fp)

    async def test_file_write_require_approval_parks_call(self):
        gate, store, _bus = _make_gate(
            self._policy(AccessLevel.REQUIRE_APPROVAL),
        )
        tc = _make_tool_call("file_write", {
            "path": "/tmp/test.txt", "content": "hello",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert "APPROVAL REQUIRED" in result["error"]
        pending = store.get_oldest_pending()
        assert pending is not None
        assert pending.tool_name == "file_write"

    async def test_file_write_deny_blocks(self):
        fp = FileAccessPolicy(
            rules=(FileAccessRule(
                paths=("/etc/**",),
                write=AccessLevel.DENY,
                reason="system files",
            ),),
        )
        gate, store, _bus = _make_gate(ToolApprovalPolicy(file_policy=fp))
        tc = _make_tool_call("file_write", {
            "path": "/etc/passwd", "content": "x",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert "BLOCKED" in result["error"]
        assert store.get_oldest_pending() is None

    async def test_file_write_allow_executes(self):
        gate, store, _bus = _make_gate(
            self._policy(AccessLevel.ALLOW),
        )
        tc = _make_tool_call("file_write", {
            "path": "/tmp/test.txt", "content": "hello",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert result == {"ok": True}
        assert store.get_oldest_pending() is None

    async def test_file_read_allow_by_default(self):
        gate, store, _bus = _make_gate(self._policy())
        tc = _make_tool_call("file_read", {"path": "/tmp/test.txt"})
        result = await gate.execute_openai_tool_call(tc)

        assert result == {"ok": True}

    async def test_file_delete_require_approval(self):
        fp = FileAccessPolicy(
            default_delete=AccessLevel.REQUIRE_APPROVAL,
        )
        gate, store, _bus = _make_gate(
            ToolApprovalPolicy(file_policy=fp),
        )
        tc = _make_tool_call("file_delete", {"path": "/tmp/test.txt"})
        result = await gate.execute_openai_tool_call(tc)

        assert "APPROVAL REQUIRED" in result["error"]
        assert store.get_oldest_pending() is not None


# ---------------------------------------------------------------------------
# 2. Gate handles network tools through ToolApprovalPolicy
# ---------------------------------------------------------------------------


class TestGateNetworkToolIntegration:
    async def test_web_fetch_deny_blocks(self):
        np = NetworkAccessPolicy(
            rules=(NetworkAccessRule(
                hosts=("*.onion",),
                policy=AccessLevel.DENY,
                reason="anonymous network",
            ),),
        )
        gate, store, _bus = _make_gate(
            ToolApprovalPolicy(network_policy=np),
        )
        tc = _make_tool_call("web_fetch", {
            "url": "https://hidden.onion/page",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert "BLOCKED" in result["error"]
        assert store.get_oldest_pending() is None

    async def test_web_fetch_require_approval_parks(self):
        np = NetworkAccessPolicy(
            rules=(NetworkAccessRule(
                hosts=("pastebin.com",),
                policy=AccessLevel.REQUIRE_APPROVAL,
                reason="content sharing",
            ),),
        )
        gate, store, _bus = _make_gate(
            ToolApprovalPolicy(network_policy=np),
        )
        tc = _make_tool_call("web_fetch", {
            "url": "https://pastebin.com/raw/abc",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert "APPROVAL REQUIRED" in result["error"]
        assert store.get_oldest_pending() is not None

    async def test_web_fetch_allow_executes(self):
        np = NetworkAccessPolicy(default=AccessLevel.ALLOW)
        gate, store, _bus = _make_gate(
            ToolApprovalPolicy(network_policy=np),
        )
        tc = _make_tool_call("web_fetch", {
            "url": "https://example.com",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert result == {"ok": True}


# ---------------------------------------------------------------------------
# 3. Resolvers work correctly for file/network tools
# ---------------------------------------------------------------------------


class TestResolversWithFileTools:
    def _require_approval_policy(self) -> ToolApprovalPolicy:
        fp = FileAccessPolicy(
            default_write=AccessLevel.REQUIRE_APPROVAL,
        )
        return ToolApprovalPolicy(file_policy=fp)

    async def test_always_approve_executes(self):
        gate, store, _bus = _make_gate(
            self._require_approval_policy(),
            resolver=AlwaysApproveResolver(),
        )
        tc = _make_tool_call("file_write", {
            "path": "/tmp/test.txt", "content": "hello",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert result == {"ok": True}
        assert store.get_oldest_pending() is None

    async def test_always_deny_blocks(self):
        gate, store, _bus = _make_gate(
            self._require_approval_policy(),
            resolver=AlwaysDenyResolver(),
        )
        tc = _make_tool_call("file_write", {
            "path": "/tmp/test.txt", "content": "hello",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert "DENIED" in result["error"]
        assert store.get_oldest_pending() is None

    async def test_interactive_resolver_parks(self):
        gate, store, bus = _make_gate(
            self._require_approval_policy(),
        )
        tc = _make_tool_call("file_write", {
            "path": "/tmp/test.txt", "content": "hello",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert "APPROVAL REQUIRED" in result["error"]
        assert store.get_oldest_pending() is not None

        messages = []
        bus.subscribe("ui_message", lambda msg: messages.append(msg))
        bus.poll()
        assert len(messages) == 1
        assert messages[0].payload.update_type == UpdateType.APPROVAL

    async def test_deny_verdict_ignores_resolver(self):
        """DENY should hard-block even with AlwaysApproveResolver."""
        fp = FileAccessPolicy(
            rules=(FileAccessRule(
                paths=("/etc/**",),
                write=AccessLevel.DENY,
                reason="system files",
            ),),
        )
        gate, store, _bus = _make_gate(
            ToolApprovalPolicy(file_policy=fp),
            resolver=AlwaysApproveResolver(),
        )
        tc = _make_tool_call("file_write", {
            "path": "/etc/passwd", "content": "x",
        })
        result = await gate.execute_openai_tool_call(tc)

        assert "BLOCKED" in result["error"]


# ---------------------------------------------------------------------------
# 4. Job CRUD syncs schedules to APScheduler
# ---------------------------------------------------------------------------


class TestSchedulerSync:
    @pytest.fixture()
    def job_store(self, tmp_path):
        from tank_backend.jobs.store import JobStore
        store = JobStore(db_path=tmp_path / "jobs.db")
        yield store
        store.close()

    @pytest.fixture()
    def mock_runner(self):
        from tank_backend.jobs.models import JobRunResult
        runner = AsyncMock()
        runner.execute = AsyncMock(return_value=JobRunResult(
            run_id="r1", job_id="j1", status="succeeded",
        ))
        return runner

    async def test_job_creation_registers_schedule(
        self, job_store, mock_runner,
    ):
        from tank_backend.jobs.models import JobDefinition
        from tank_backend.jobs.scheduler import CronScheduler

        scheduler = CronScheduler(job_store, mock_runner)
        await scheduler.start()

        job = JobDefinition.from_dict({
            "name": "test_sync",
            "prompt": "Do something",
            "schedule": "0 9 * * *",
        })
        job_store.save_job(job)
        await scheduler.sync_schedules()

        schedules = await scheduler._scheduler.get_schedules()
        ids = {s.id for s in schedules}
        assert f"tank_job_{job.id}" in ids

        await scheduler.stop()

    async def test_job_deletion_removes_schedule(
        self, job_store, mock_runner,
    ):
        from tank_backend.jobs.models import JobDefinition
        from tank_backend.jobs.scheduler import CronScheduler

        scheduler = CronScheduler(job_store, mock_runner)
        await scheduler.start()

        job = JobDefinition.from_dict({
            "name": "test_del_sync",
            "prompt": "Do something",
            "schedule": "0 9 * * *",
        })
        job_store.save_job(job)
        await scheduler.sync_schedules()

        job_store.delete_job(job.id)
        await scheduler.sync_schedules()

        schedules = await scheduler._scheduler.get_schedules()
        ids = {s.id for s in schedules}
        assert f"tank_job_{job.id}" not in ids

        await scheduler.stop()

    async def test_disabled_job_not_scheduled(
        self, job_store, mock_runner,
    ):
        from tank_backend.jobs.models import JobDefinition
        from tank_backend.jobs.scheduler import CronScheduler

        scheduler = CronScheduler(job_store, mock_runner)
        await scheduler.start()

        job = JobDefinition.from_dict({
            "name": "test_disabled",
            "prompt": "Do something",
            "schedule": "0 9 * * *",
            "enabled": False,
        })
        job_store.save_job(job)
        await scheduler.sync_schedules()

        schedules = await scheduler._scheduler.get_schedules()
        ids = {s.id for s in schedules}
        assert f"tank_job_{job.id}" not in ids

        await scheduler.stop()

    async def test_enable_job_adds_schedule(
        self, job_store, mock_runner,
    ):
        from tank_backend.jobs.models import JobDefinition
        from tank_backend.jobs.scheduler import CronScheduler

        scheduler = CronScheduler(job_store, mock_runner)
        await scheduler.start()

        job = JobDefinition.from_dict({
            "name": "test_enable",
            "prompt": "Do something",
            "schedule": "0 9 * * *",
            "enabled": False,
        })
        job_store.save_job(job)
        await scheduler.sync_schedules()

        # Not scheduled
        schedules = await scheduler._scheduler.get_schedules()
        assert not any(s.id == f"tank_job_{job.id}" for s in schedules)

        # Enable and re-sync
        job_store.set_enabled(job.id, True)
        await scheduler.sync_schedules()

        schedules = await scheduler._scheduler.get_schedules()
        assert any(s.id == f"tank_job_{job.id}" for s in schedules)

        await scheduler.stop()


# ---------------------------------------------------------------------------
# 5. ToolApprovalPolicy routes to correct policy per tool type
# ---------------------------------------------------------------------------


class TestToolApprovalPolicyRouting:
    def _full_policy(self) -> ToolApprovalPolicy:
        from tank_backend.policy.command_security import (
            CommandSecurityPolicy,
        )
        return ToolApprovalPolicy(
            command_policy=CommandSecurityPolicy.from_dict({}),
            file_policy=FileAccessPolicy(
                default_write=AccessLevel.REQUIRE_APPROVAL,
                default_read=AccessLevel.ALLOW,
            ),
            network_policy=NetworkAccessPolicy(
                default=AccessLevel.ALLOW,
            ),
        )

    def test_command_tool_uses_command_policy(self):
        v = self._full_policy().evaluate(
            "run_command", {"command": "ls"},
        )
        assert v.level == AccessLevel.ALLOW
        assert v.policy == "command"

    def test_file_write_uses_file_policy(self):
        v = self._full_policy().evaluate(
            "file_write", {"path": "/tmp/x"},
        )
        assert v.level == AccessLevel.REQUIRE_APPROVAL
        assert v.policy == "file"

    def test_file_read_uses_file_policy(self):
        v = self._full_policy().evaluate(
            "file_read", {"path": "/tmp/x"},
        )
        assert v.level == AccessLevel.ALLOW
        assert v.policy == "file"

    def test_web_tool_uses_network_policy(self):
        v = self._full_policy().evaluate(
            "web_fetch", {"url": "https://example.com"},
        )
        assert v.level == AccessLevel.ALLOW
        assert v.policy == "network"

    def test_unknown_tool_auto_approved(self):
        v = self._full_policy().evaluate(
            "calculate", {"expression": "2+2"},
        )
        assert v.level == AccessLevel.ALLOW
        assert v.policy == "tool"

    def test_file_tool_without_path_allows(self):
        v = self._full_policy().evaluate("file_write", {})
        assert v.level == AccessLevel.ALLOW

    def test_web_tool_without_url_allows(self):
        v = self._full_policy().evaluate("web_fetch", {})
        assert v.level == AccessLevel.ALLOW
