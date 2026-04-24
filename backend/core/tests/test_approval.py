"""Tests for the approval system: ToolApprovalPolicy, make_approval_id."""

from __future__ import annotations

from tank_backend.agents.approval import (
    ToolApprovalPolicy,
    make_approval_id,
)


def test_make_approval_id_unique():
    ids = {make_approval_id() for _ in range(100)}
    assert len(ids) == 100


# ---------------------------------------------------------------------------
# ToolApprovalPolicy tests
# ---------------------------------------------------------------------------

class TestToolApprovalPolicy:
    def test_require_approval(self):
        policy = ToolApprovalPolicy(require_approval={"run_command", "persistent_shell"})
        assert policy.needs_approval("run_command") is True
        assert policy.needs_approval("persistent_shell") is True

    def test_always_approve(self):
        policy = ToolApprovalPolicy(always_approve={"weather", "get_time"})
        assert policy.needs_approval("weather") is False
        assert policy.needs_approval("get_time") is False

    def test_unlisted_defaults_to_no_approval(self):
        policy = ToolApprovalPolicy(require_approval={"run_command"})
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
        policy = ToolApprovalPolicy(require_approval={"run_command"})
        policy.record_approved("run_command")
        assert policy.needs_approval("run_command") is True

    def test_empty_policy_approves_all(self):
        policy = ToolApprovalPolicy()
        assert policy.needs_approval("anything") is False

    def test_hardcoded_sandbox_tools_always_require_approval(self):
        """run_command and persistent_shell require approval even with empty config."""
        policy = ToolApprovalPolicy()
        assert policy.needs_approval("run_command") is True
        assert policy.needs_approval("persistent_shell") is True

    def test_hardcoded_cannot_be_overridden_by_always_approve(self):
        """Putting run_command in always_approve doesn't bypass hardcoded check."""
        policy = ToolApprovalPolicy(always_approve={"run_command"})
        assert policy.needs_approval("run_command") is True

    def test_file_tools_not_hardcoded(self):
        """File tools handle their own approval — not in hardcoded set."""
        policy = ToolApprovalPolicy()
        assert policy.needs_approval("file_read") is False
        assert policy.needs_approval("file_write") is False
        assert policy.needs_approval("file_delete") is False
        assert policy.needs_approval("file_list") is False
