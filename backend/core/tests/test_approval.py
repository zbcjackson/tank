"""Tests for the approval system: ApprovalManager, ToolApprovalPolicy, dataclasses."""

from __future__ import annotations

import asyncio

import pytest

from tank_backend.agents.approval import (
    ApprovalManager,
    ToolApprovalPolicy,
    ApprovalRequest,
    ApprovalResult,
    make_approval_id,
)
from tank_backend.agents.base import AgentOutputType

# ---------------------------------------------------------------------------
# Dataclass / enum tests
# ---------------------------------------------------------------------------

def test_approval_needed_in_agent_output_type():
    assert hasattr(AgentOutputType, "APPROVAL_NEEDED")
    # Ensure it's a distinct enum member
    assert AgentOutputType.APPROVAL_NEEDED != AgentOutputType.TOOL_CALLING


def test_approval_request_is_frozen():
    req = ApprovalRequest(
        approval_id="abc",
        tool_name="sandbox_exec",
        tool_args={"code": "print(1)"},
        description="Run Python code: print(1)",
        session_id="s1",
    )
    assert req.approval_id == "abc"
    with pytest.raises(AttributeError):
        req.approval_id = "xyz"  # type: ignore[misc]


def test_approval_result_defaults():
    result = ApprovalResult(approval_id="abc", approved=True)
    assert result.reason == ""


def test_make_approval_id_unique():
    ids = {make_approval_id() for _ in range(100)}
    assert len(ids) == 100


# ---------------------------------------------------------------------------
# ToolApprovalPolicy tests
# ---------------------------------------------------------------------------

class TestToolApprovalPolicy:
    def test_require_approval(self):
        policy = ToolApprovalPolicy(require_approval={"sandbox_exec", "sandbox_bash"})
        assert policy.needs_approval("sandbox_exec") is True
        assert policy.needs_approval("sandbox_bash") is True

    def test_always_approve(self):
        policy = ToolApprovalPolicy(always_approve={"weather", "get_time"})
        assert policy.needs_approval("weather") is False
        assert policy.needs_approval("get_time") is False

    def test_unlisted_defaults_to_no_approval(self):
        policy = ToolApprovalPolicy(require_approval={"sandbox_exec"})
        assert policy.needs_approval("unknown_tool") is False

    def test_first_time_approval(self):
        policy = ToolApprovalPolicy(require_approval_first_time={"web_search"})
        # First time → needs approval
        assert policy.needs_approval("web_search") is True
        # Record approval
        policy.record_approved("web_search")
        # Second time → auto-approve
        assert policy.needs_approval("web_search") is False

    def test_first_time_reset(self):
        policy = ToolApprovalPolicy(require_approval_first_time={"web_search"})
        policy.record_approved("web_search")
        assert policy.needs_approval("web_search") is False
        policy.reset()
        assert policy.needs_approval("web_search") is True

    def test_require_approval_always_asks(self):
        """require_approval ignores record_approved — always asks."""
        policy = ToolApprovalPolicy(require_approval={"sandbox_exec"})
        policy.record_approved("sandbox_exec")
        assert policy.needs_approval("sandbox_exec") is True

    def test_empty_policy_approves_all(self):
        policy = ToolApprovalPolicy()
        assert policy.needs_approval("anything") is False

    def test_hardcoded_sandbox_tools_always_require_approval(self):
        """sandbox_exec and sandbox_bash require approval even with empty config."""
        policy = ToolApprovalPolicy()
        assert policy.needs_approval("sandbox_exec") is True
        assert policy.needs_approval("sandbox_bash") is True

    def test_hardcoded_cannot_be_overridden_by_always_approve(self):
        """Putting sandbox_exec in always_approve doesn't bypass hardcoded check."""
        policy = ToolApprovalPolicy(always_approve={"sandbox_exec"})
        assert policy.needs_approval("sandbox_exec") is True

    def test_file_tools_not_hardcoded(self):
        """File tools handle their own approval — not in hardcoded set."""
        policy = ToolApprovalPolicy()
        assert policy.needs_approval("file_read") is False
        assert policy.needs_approval("file_write") is False
        assert policy.needs_approval("file_delete") is False
        assert policy.needs_approval("file_list") is False


# ---------------------------------------------------------------------------
# ApprovalManager tests
# ---------------------------------------------------------------------------

class TestApprovalManager:
    async def test_request_and_resolve(self):
        manager = ApprovalManager(timeout=10.0)
        req = ApprovalRequest(
            approval_id="test1",
            tool_name="sandbox_exec",
            tool_args={"code": "print(1)"},
            description="Run Python code",
            session_id="s1",
        )

        async def resolve_soon():
            await asyncio.sleep(0.01)
            manager.resolve("test1", approved=True, reason="User said yes")

        asyncio.get_event_loop().create_task(resolve_soon())
        result = await manager.request_approval(req)

        assert result.approved is True
        assert result.approval_id == "test1"
        assert result.reason == "User said yes"

    async def test_request_and_reject(self):
        manager = ApprovalManager(timeout=10.0)
        req = ApprovalRequest(
            approval_id="test2",
            tool_name="sandbox_bash",
            tool_args={"command": "rm -rf /"},
            description="Run bash: rm -rf /",
            session_id="s1",
        )

        async def reject_soon():
            await asyncio.sleep(0.01)
            manager.resolve("test2", approved=False, reason="Too dangerous")

        asyncio.get_event_loop().create_task(reject_soon())
        result = await manager.request_approval(req)

        assert result.approved is False
        assert result.reason == "Too dangerous"

    async def test_timeout_auto_reject(self):
        manager = ApprovalManager(timeout=0.05)
        req = ApprovalRequest(
            approval_id="timeout1",
            tool_name="sandbox_exec",
            tool_args={},
            description="test",
            session_id="s1",
        )

        result = await manager.request_approval(req)

        assert result.approved is False
        assert "timed out" in result.reason.lower()

    async def test_get_pending_filtering(self):
        manager = ApprovalManager(timeout=10.0)

        req1 = ApprovalRequest(
            approval_id="p1", tool_name="t1", tool_args={},
            description="d1", session_id="s1",
        )
        req2 = ApprovalRequest(
            approval_id="p2", tool_name="t2", tool_args={},
            description="d2", session_id="s2",
        )

        # Start both requests without awaiting (they'll hang until resolved)
        task1 = asyncio.create_task(manager.request_approval(req1))
        task2 = asyncio.create_task(manager.request_approval(req2))
        await asyncio.sleep(0.01)  # Let tasks register

        # All pending
        all_pending = manager.get_pending()
        assert len(all_pending) == 2

        # Filter by session
        s1_pending = manager.get_pending(session_id="s1")
        assert len(s1_pending) == 1
        assert s1_pending[0].approval_id == "p1"

        # Cleanup
        manager.resolve("p1", approved=True)
        manager.resolve("p2", approved=True)
        await task1
        await task2

    async def test_resolve_unknown_returns_false(self):
        manager = ApprovalManager()
        assert manager.resolve("nonexistent", approved=True) is False

    async def test_resolve_already_resolved_returns_false(self):
        manager = ApprovalManager(timeout=10.0)
        req = ApprovalRequest(
            approval_id="dup1", tool_name="t1", tool_args={},
            description="d1", session_id="s1",
        )

        task = asyncio.create_task(manager.request_approval(req))
        await asyncio.sleep(0.01)

        assert manager.resolve("dup1", approved=True) is True
        assert manager.resolve("dup1", approved=False) is False

        await task

    async def test_cleanup_after_resolve(self):
        manager = ApprovalManager(timeout=10.0)
        req = ApprovalRequest(
            approval_id="clean1", tool_name="t1", tool_args={},
            description="d1", session_id="s1",
        )

        async def resolve_soon():
            await asyncio.sleep(0.01)
            manager.resolve("clean1", approved=True)

        asyncio.get_event_loop().create_task(resolve_soon())
        await manager.request_approval(req)

        # Should be cleaned up after await returns
        assert len(manager.get_pending()) == 0
