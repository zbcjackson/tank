"""Tests for the approval system: ToolApprovalPolicy, make_approval_id."""

from __future__ import annotations

from tank_backend.agents.approval import ToolApprovalPolicy, make_approval_id
from tank_backend.policy.command_security import CommandSecurityPolicy


def test_make_approval_id_unique():
    ids = {make_approval_id() for _ in range(100)}
    assert len(ids) == 100


# ---------------------------------------------------------------------------
# ToolApprovalPolicy tests
# ---------------------------------------------------------------------------

class TestToolApprovalPolicy:
    def test_command_tools_require_approval_without_policy(self):
        """Without CommandSecurityPolicy, command tools always require approval."""
        policy = ToolApprovalPolicy()
        assert policy.needs_approval("run_command") is True
        assert policy.needs_approval("persistent_shell") is True

    def test_command_tools_require_approval_without_command_arg(self):
        """Command tools with no 'command' arg require approval."""
        cmd_policy = CommandSecurityPolicy.from_dict({})
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        assert policy.needs_approval("run_command") is True
        assert policy.needs_approval("run_command", {}) is True
        assert policy.needs_approval("run_command", {"timeout": 10}) is True

    def test_safe_command_auto_approved(self):
        cmd_policy = CommandSecurityPolicy.from_dict({})
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        assert policy.needs_approval("run_command", {"command": "ls -la"}) is False
        assert policy.needs_approval("persistent_shell", {"command": "pwd"}) is False

    def test_dangerous_command_requires_approval(self):
        cmd_policy = CommandSecurityPolicy.from_dict({})
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        assert policy.needs_approval("run_command", {"command": "rm -rf /"}) is True
        assert policy.needs_approval("persistent_shell", {"command": "git push --force"}) is True

    def test_unknown_command_requires_approval(self):
        cmd_policy = CommandSecurityPolicy.from_dict({})
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        assert policy.needs_approval("run_command", {"command": "terraform apply"}) is True

    def test_non_command_tools_auto_approved(self):
        """All non-command tools are auto-approved."""
        policy = ToolApprovalPolicy()
        assert policy.needs_approval("weather") is False
        assert policy.needs_approval("get_time") is False
        assert policy.needs_approval("calculator") is False
        assert policy.needs_approval("unknown_tool") is False

    def test_file_tools_not_managed_here(self):
        """File tools handle their own approval — not managed by ToolApprovalPolicy."""
        policy = ToolApprovalPolicy()
        assert policy.needs_approval("file_read") is False
        assert policy.needs_approval("file_write") is False
        assert policy.needs_approval("file_delete") is False
        assert policy.needs_approval("file_list") is False
