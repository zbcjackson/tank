"""Tests for CommandApprovalStore — durable command approvals."""

from __future__ import annotations

from tank_backend.config.models import CommandSecurityConfig
from tank_backend.policy.command_security import CommandSecurityPolicy
from tank_backend.policy.verdict import AccessLevel

# ---------------------------------------------------------------------------
# CommandSecurityPolicy with approval_store
# ---------------------------------------------------------------------------

class _FakeApprovalStore:
    """In-memory fake for testing."""

    def __init__(self, approved: set[str] | None = None):
        self._approved = approved or set()

    def has(self, base_command: str) -> bool:
        return base_command in self._approved

    def grant(self, base_command: str, session_id: str = "") -> None:
        self._approved.add(base_command)

    def revoke(self, base_command: str) -> bool:
        if base_command in self._approved:
            self._approved.discard(base_command)
            return True
        return False

    def list_all(self) -> list[str]:
        return sorted(self._approved)


class TestDurableApprovals:
    def test_unknown_command_requires_approval(self):
        """Without approval store, unknown commands require approval."""
        policy = CommandSecurityPolicy(CommandSecurityConfig())
        verdict = policy.evaluate("mycustomtool --flag")
        assert verdict.level == AccessLevel.REQUIRE_APPROVAL

    def test_previously_approved_command_allows(self):
        """With a matching approval, the command auto-allows."""
        store = _FakeApprovalStore(approved={"mycustomtool"})
        policy = CommandSecurityPolicy(
            CommandSecurityConfig(),
            approval_store=store,
        )
        verdict = policy.evaluate("mycustomtool --flag")
        assert verdict.level == AccessLevel.ALLOW
        # The overall reason is "all segments safe" since each segment passed
        assert verdict.level == AccessLevel.ALLOW

    def test_dangerous_command_not_overridden_by_approval(self):
        """Dangerous patterns still block even if the base command is approved."""
        store = _FakeApprovalStore(approved={"rm"})
        policy = CommandSecurityPolicy(
            CommandSecurityConfig(),
            approval_store=store,
        )
        # rm -rf / matches the dangerous pattern
        verdict = policy.evaluate("rm -rf /")
        assert verdict.level == AccessLevel.DENY

    def test_safe_command_still_allows_without_store(self):
        """Safe commands auto-allow without needing the store."""
        policy = CommandSecurityPolicy(
            CommandSecurityConfig(),
            approval_store=_FakeApprovalStore(),
        )
        verdict = policy.evaluate("ls -la")
        assert verdict.level == AccessLevel.ALLOW

    def test_always_require_not_overridden(self):
        """Commands in always_require_approval list can't be overridden by store."""
        store = _FakeApprovalStore(approved={"sudo"})
        policy = CommandSecurityPolicy(
            CommandSecurityConfig(),
            approval_store=store,
        )
        verdict = policy.evaluate("sudo ls")
        assert verdict.level == AccessLevel.REQUIRE_APPROVAL

    def test_grant_then_approve(self):
        """Grant a command, then verify it auto-allows."""
        store = _FakeApprovalStore()
        policy = CommandSecurityPolicy(
            CommandSecurityConfig(),
            approval_store=store,
        )

        # Before grant — requires approval
        verdict = policy.evaluate("terraform plan")
        assert verdict.level == AccessLevel.REQUIRE_APPROVAL

        # Grant
        store.grant("terraform", session_id="test")

        # After grant — allows
        verdict = policy.evaluate("terraform plan")
        assert verdict.level == AccessLevel.ALLOW

    def test_revoke_removes_approval(self):
        """Revoking removes the durable approval."""
        store = _FakeApprovalStore(approved={"terraform"})
        policy = CommandSecurityPolicy(
            CommandSecurityConfig(),
            approval_store=store,
        )

        # Before revoke — allows
        verdict = policy.evaluate("terraform plan")
        assert verdict.level == AccessLevel.ALLOW

        # Revoke
        store.revoke("terraform")

        # After revoke — requires approval again
        verdict = policy.evaluate("terraform plan")
        assert verdict.level == AccessLevel.REQUIRE_APPROVAL

    def test_compound_command_each_segment_checked(self):
        """Each segment of a compound command is checked independently."""
        store = _FakeApprovalStore(approved={"terraform"})
        policy = CommandSecurityPolicy(
            CommandSecurityConfig(),
            approval_store=store,
        )
        # terraform is approved, but unknown_cmd isn't
        verdict = policy.evaluate("terraform plan && unknown_cmd")
        # The compound splits and evaluates each — first is ALLOW, second is REQUIRE
        # The overall result should be REQUIRE_APPROVAL
        assert verdict.level == AccessLevel.REQUIRE_APPROVAL

    def test_no_approval_store_is_noop(self):
        """When approval_store is None, behavior is unchanged."""
        policy = CommandSecurityPolicy(
            CommandSecurityConfig(),
            approval_store=None,
        )
        verdict = policy.evaluate("terraform plan")
        assert verdict.level == AccessLevel.REQUIRE_APPROVAL
