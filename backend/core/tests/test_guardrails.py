"""Tests for ToolCallGuardrailController."""

from __future__ import annotations

from tank_backend.agents.guardrails import (
    GuardrailDecision,
    ToolCallGuardrailController,
    ToolCallSignature,
)
from tank_backend.config.models import ToolGuardrailsConfig

# ---------------------------------------------------------------------------
# ToolCallSignature
# ---------------------------------------------------------------------------

class TestToolCallSignature:
    def test_from_call(self):
        sig = ToolCallSignature.from_call("run_command", '{"command": "ls"}')
        assert sig.tool_name == "run_command"
        assert len(sig.args_hash) == 16

    def test_same_args_same_hash(self):
        sig1 = ToolCallSignature.from_call("run_command", '{"command": "ls"}')
        sig2 = ToolCallSignature.from_call("run_command", '{"command": "ls"}')
        assert sig1 == sig2

    def test_different_args_different_hash(self):
        sig1 = ToolCallSignature.from_call("run_command", '{"command": "ls"}')
        sig2 = ToolCallSignature.from_call("run_command", '{"command": "pwd"}')
        assert sig1 != sig2


# ---------------------------------------------------------------------------
# Exact repeat failure detection
# ---------------------------------------------------------------------------

class TestExactRepeatFailure:
    def setup_method(self):
        self.ctrl = ToolCallGuardrailController(
            ToolGuardrailsConfig(
                exact_repeat_warn_after=2,
                exact_repeat_block_after=4,
            )
        )
        self.sig = ToolCallSignature.from_call("run_command", '{"command": "bad"}')

    def test_first_failure_allows(self):
        decision = self.ctrl.record_result(self.sig, failed=True)
        assert decision.action == "allow"

    def test_warn_after_threshold(self):
        self.ctrl.record_result(self.sig, failed=True)
        decision = self.ctrl.record_result(self.sig, failed=True)
        assert decision.action == "warn"
        assert "run_command" in decision.reason

    def test_block_after_threshold(self):
        for _ in range(3):
            self.ctrl.record_result(self.sig, failed=True)
        decision = self.ctrl.record_result(self.sig, failed=True)
        assert decision.action == "block"
        assert "blocked" in decision.reason.lower()

    def test_different_args_tracked_separately(self):
        sig2 = ToolCallSignature.from_call("run_command", '{"command": "other"}')
        self.ctrl.record_result(self.sig, failed=True)
        decision = self.ctrl.record_result(sig2, failed=True)
        # Only 1 failure for sig2 — should allow
        assert decision.action == "allow"


# ---------------------------------------------------------------------------
# Same-tool failure detection
# ---------------------------------------------------------------------------

class TestSameToolFailure:
    def setup_method(self):
        self.ctrl = ToolCallGuardrailController(
            ToolGuardrailsConfig(
                exact_repeat_warn_after=10,  # high so we only trigger same-tool
                exact_repeat_block_after=20,
                same_tool_fail_warn_after=3,
                same_tool_fail_block_after=6,
            )
        )

    def test_warn_after_multiple_different_args(self):
        for i in range(3):
            sig = ToolCallSignature.from_call("file_write", f'{{"path": "f{i}"}}')
            decision = self.ctrl.record_result(sig, failed=True)

        assert decision.action == "warn"

    def test_block_after_many_failures(self):
        for i in range(6):
            sig = ToolCallSignature.from_call("file_write", f'{{"path": "f{i}"}}')
            decision = self.ctrl.record_result(sig, failed=True)

        assert decision.action == "block"


# ---------------------------------------------------------------------------
# No-progress detection (idempotent tools)
# ---------------------------------------------------------------------------

class TestNoProgressDetection:
    def setup_method(self):
        self.ctrl = ToolCallGuardrailController(
            ToolGuardrailsConfig(
                no_progress_warn_after=3,
                no_progress_block_after=5,
            )
        )
        self.sig = ToolCallSignature.from_call("file_read", '{"path": "/tmp/x"}')

    def test_first_call_allows(self):
        decision = self.ctrl.record_result(
            self.sig, failed=False, result_content="hello", idempotent=True,
        )
        assert decision.action == "allow"

    def test_different_results_allow(self):
        self.ctrl.record_result(
            self.sig, failed=False, result_content="hello", idempotent=True,
        )
        decision = self.ctrl.record_result(
            self.sig, failed=False, result_content="world", idempotent=True,
        )
        assert decision.action == "allow"

    def test_identical_results_warn(self):
        # First call sets the baseline
        self.ctrl.record_result(
            self.sig, failed=False, result_content="same", idempotent=True,
        )
        # Identical results accumulate
        for _ in range(3):
            decision = self.ctrl.record_result(
                self.sig, failed=False, result_content="same", idempotent=True,
            )
        assert decision.action == "warn"

    def test_identical_results_block(self):
        self.ctrl.record_result(
            self.sig, failed=False, result_content="same", idempotent=True,
        )
        for _ in range(5):
            decision = self.ctrl.record_result(
                self.sig, failed=False, result_content="same", idempotent=True,
            )
        assert decision.action == "block"

    def test_non_idempotent_tool_no_detection(self):
        """Non-idempotent tools don't trigger no-progress detection."""
        self.ctrl.record_result(
            self.sig, failed=False, result_content="same", idempotent=False,
        )
        for _ in range(10):
            decision = self.ctrl.record_result(
                self.sig, failed=False, result_content="same", idempotent=False,
            )
        assert decision.action == "allow"


# ---------------------------------------------------------------------------
# Reset and disabled
# ---------------------------------------------------------------------------

class TestGuardrailReset:
    def test_reset_clears_state(self):
        ctrl = ToolCallGuardrailController(
            ToolGuardrailsConfig(exact_repeat_warn_after=2)
        )
        sig = ToolCallSignature.from_call("x", "y")
        ctrl.record_result(sig, failed=True)
        ctrl.reset()
        # After reset, count starts fresh
        decision = ctrl.record_result(sig, failed=True)
        assert decision.action == "allow"

    def test_disabled_always_allows(self):
        ctrl = ToolCallGuardrailController(
            ToolGuardrailsConfig(enabled=False)
        )
        sig = ToolCallSignature.from_call("x", "y")
        for _ in range(100):
            decision = ctrl.record_result(sig, failed=True)
        assert decision.action == "allow"


# ---------------------------------------------------------------------------
# GuardrailDecision helpers
# ---------------------------------------------------------------------------

class TestGuardrailDecision:
    def test_should_warn(self):
        d = GuardrailDecision(action="warn", reason="test")
        assert d.should_warn is True
        assert d.should_block is False

    def test_should_block(self):
        d = GuardrailDecision(action="block", reason="test")
        assert d.should_block is True
        assert d.should_warn is False

    def test_allow(self):
        d = GuardrailDecision(action="allow")
        assert d.should_warn is False
        assert d.should_block is False
