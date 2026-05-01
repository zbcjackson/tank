"""Tests for the approval system: ToolApprovalPolicy, make_approval_id."""

from __future__ import annotations

from tank_backend.agents.approval import ToolApprovalPolicy, make_approval_id
from tank_backend.config.models import CommandSecurityConfig
from tank_backend.policy.command_security import CommandSecurityPolicy
from tank_backend.policy.verdict import AccessLevel


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
        assert policy.evaluate("run_command").level == AccessLevel.REQUIRE_APPROVAL
        assert policy.evaluate("persistent_shell").level == AccessLevel.REQUIRE_APPROVAL

    def test_command_tools_require_approval_without_command_arg(self):
        """Command tools with no 'command' arg require approval."""
        cmd_policy = CommandSecurityPolicy(CommandSecurityConfig())
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        assert policy.evaluate("run_command").level == AccessLevel.REQUIRE_APPROVAL
        assert policy.evaluate("run_command", {}).level == AccessLevel.REQUIRE_APPROVAL
        assert policy.evaluate("run_command", {"timeout": 10}).level == AccessLevel.REQUIRE_APPROVAL

    def test_safe_command_auto_approved(self):
        cmd_policy = CommandSecurityPolicy(CommandSecurityConfig())
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        assert policy.evaluate("run_command", {"command": "ls -la"}).level == AccessLevel.ALLOW
        assert policy.evaluate("persistent_shell", {"command": "pwd"}).level == AccessLevel.ALLOW

    def test_dangerous_command_requires_approval(self):
        cmd_policy = CommandSecurityPolicy(CommandSecurityConfig())
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        v1 = policy.evaluate("run_command", {"command": "rm -rf /"})
        assert v1.level != AccessLevel.ALLOW
        v2 = policy.evaluate(
            "persistent_shell", {"command": "git push --force"},
        )
        assert v2.level != AccessLevel.ALLOW

    def test_unknown_command_requires_approval(self):
        cmd_policy = CommandSecurityPolicy(CommandSecurityConfig())
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        v = policy.evaluate(
            "run_command", {"command": "terraform apply"},
        )
        assert v.level == AccessLevel.REQUIRE_APPROVAL

    def test_non_command_tools_auto_approved(self):
        """All non-command tools are auto-approved."""
        policy = ToolApprovalPolicy()
        assert policy.evaluate("weather").level == AccessLevel.ALLOW
        assert policy.evaluate("get_time").level == AccessLevel.ALLOW
        assert policy.evaluate("calculator").level == AccessLevel.ALLOW
        assert policy.evaluate("unknown_tool").level == AccessLevel.ALLOW

    def test_file_tools_not_managed_here(self):
        """File tools handle their own approval — not managed by ToolApprovalPolicy."""
        policy = ToolApprovalPolicy()
        assert policy.evaluate("file_read").level == AccessLevel.ALLOW
        assert policy.evaluate("file_write").level == AccessLevel.ALLOW
        assert policy.evaluate("file_delete").level == AccessLevel.ALLOW
        assert policy.evaluate("file_list").level == AccessLevel.ALLOW
