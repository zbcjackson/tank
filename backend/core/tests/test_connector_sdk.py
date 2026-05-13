"""Unit tests for :mod:`tank_contracts.connector_sdk`.

Covers the six extracted helpers individually; plugin migrations
(Phase 11 Tasks #84-#86) rely on these tests to establish the SDK's
byte-for-byte equivalence to the inlined helpers they replace.

Runs against the contracts package directly — no plugin or backend
imports — so failures point at the SDK rather than any consumer.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from tank_contracts.connector import Identity
from tank_contracts.connector_sdk import (
    APPROVAL_ACTION_PREFIX,
    APPROVAL_CHOICE_ALLOW_FOREVER,
    APPROVAL_CHOICE_ALLOW_ONCE,
    APPROVAL_CHOICE_DENY,
    APPROVAL_VALID_CHOICES,
    BackgroundTaskRunner,
    build_outcome_text,
    build_prompt_text,
    decode_action,
    encode_action,
    require_string_field,
    truncate_for_platform,
    validate_spec,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_choice_literal_values_are_stable(self) -> None:
        """These values are the wire strings shared with the broker +
        every plugin — changing them silently breaks every existing
        pending-approval row in the DB. Pinning them explicitly catches
        accidental typos."""
        assert APPROVAL_CHOICE_ALLOW_ONCE == "allow_once"
        assert APPROVAL_CHOICE_ALLOW_FOREVER == "allow_forever"
        assert APPROVAL_CHOICE_DENY == "deny"
        assert APPROVAL_ACTION_PREFIX == "approve"

    def test_valid_choices_set_matches_individual_constants(self) -> None:
        assert frozenset({
            APPROVAL_CHOICE_ALLOW_ONCE,
            APPROVAL_CHOICE_ALLOW_FOREVER,
            APPROVAL_CHOICE_DENY,
        }) == APPROVAL_VALID_CHOICES


# ---------------------------------------------------------------------------
# factory.validate_spec
# ---------------------------------------------------------------------------


class TestValidateSpec:
    def test_happy_path(self) -> None:
        name, cfg = validate_spec(
            {"instance": "my-bot", "config": {"bot_token": "x"}},
            plugin_name="connector-test",
        )
        assert name == "my-bot"
        assert cfg == {"bot_token": "x"}

    def test_missing_instance_defaults_to_empty_string(self) -> None:
        """Plugin factories fall back to a platform-default name when
        instance is empty; validate_spec just hands them back the ``""``
        and leaves that decision to the caller."""
        name, cfg = validate_spec(
            {"config": {"bot_token": "x"}},
            plugin_name="connector-test",
        )
        assert name == ""
        assert cfg == {"bot_token": "x"}

    def test_missing_config_returns_empty_dict(self) -> None:
        """Downstream ``require_string_field`` calls raise the right
        "missing field" error when they run against an empty dict —
        which is the shape we want to hand them."""
        name, cfg = validate_spec({"instance": "x"}, plugin_name="t")
        assert name == "x"
        assert cfg == {}

    def test_none_config_returns_empty_dict(self) -> None:
        name, cfg = validate_spec(
            {"instance": "x", "config": None}, plugin_name="t",
        )
        assert cfg == {}

    def test_non_mapping_config_raises_with_plugin_context(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            validate_spec(
                {"instance": "my-bot", "config": "not-a-dict"},
                plugin_name="connector-test",
            )
        msg = str(exc_info.value)
        assert "connector-test" in msg
        assert "my-bot" in msg
        assert "config" in msg
        assert "mapping" in msg
        # Observed type name helps debug weird YAML-parse bugs.
        assert "str" in msg


# ---------------------------------------------------------------------------
# factory.require_string_field
# ---------------------------------------------------------------------------


class TestRequireStringField:
    def test_happy_path_returns_value(self) -> None:
        got = require_string_field(
            {"bot_token": "xoxb-abc"}, "bot_token",
            plugin_name="connector-test", instance_name="my-bot",
        )
        assert got == "xoxb-abc"

    def test_missing_field_raises(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            require_string_field(
                {}, "bot_token",
                plugin_name="connector-test", instance_name="my-bot",
            )
        msg = str(exc_info.value)
        assert "connector-test" in msg
        assert "my-bot" in msg
        assert "config.bot_token" in msg
        assert "required" in msg

    def test_whitespace_only_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="required"):
            require_string_field(
                {"bot_token": "   "}, "bot_token",
                plugin_name="t", instance_name="x",
            )

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="required"):
            require_string_field(
                {"bot_token": ""}, "bot_token",
                plugin_name="t", instance_name="x",
            )

    def test_non_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="required"):
            require_string_field(
                {"bot_token": 42}, "bot_token",
                plugin_name="t", instance_name="x",
            )

    def test_env_var_hint_appears_in_error_message(self) -> None:
        """Operators who hit the error should see the exact env-var
        incantation Tank's docs tell them to set."""
        with pytest.raises(ValueError) as exc_info:
            require_string_field(
                {}, "bot_token",
                plugin_name="connector-slack", instance_name="my-bot",
                env_var="SLACK_BOT_TOKEN",
            )
        msg = str(exc_info.value)
        assert "SLACK_BOT_TOKEN" in msg
        assert "${SLACK_BOT_TOKEN}" in msg


# ---------------------------------------------------------------------------
# approval.build_prompt_text
# ---------------------------------------------------------------------------


class TestBuildPromptText:
    def test_sender_with_display_name_shows_parenthesised_identity(
        self,
    ) -> None:
        sender = Identity(
            platform="telegram",
            external_id="tg:user:99",
            display_name="Alice",
        )
        text = build_prompt_text(sender, "hello tank")
        assert "New sender wants to talk to me:" in text
        assert "Alice (tg:user:99)" in text
        assert "• message preview: hello tank" in text

    def test_sender_without_display_name_shows_bare_identity(self) -> None:
        """Avoid the ``"" (tg:user:99)`` ugly rendering when no
        display name is attached to the incoming event."""
        sender = Identity(
            platform="telegram",
            external_id="tg:user:99",
        )
        text = build_prompt_text(sender, "hi")
        # No parenthesised form — just the external_id.
        assert "• tg:user:99" in text
        assert "()" not in text

    def test_preview_passes_through_verbatim(self) -> None:
        """Truncation is a separate concern — build_prompt_text is
        dumb about length so callers can cap per-platform."""
        long_preview = "x" * 500
        sender = Identity(platform="t", external_id="a")
        text = build_prompt_text(sender, long_preview)
        assert long_preview in text


# ---------------------------------------------------------------------------
# approval.build_outcome_text
# ---------------------------------------------------------------------------


class TestBuildOutcomeText:
    """``build_outcome_text`` renders the post-click confirmation that
    every connector swaps in where the approval prompt used to be.
    The tests pin the exact shape so future copy changes land in one
    place (the SDK) rather than drifting per-plugin."""

    def test_allow_forever_happy_path(self) -> None:
        sender = Identity(
            platform="telegram",
            external_id="tg:user:99",
            display_name="Alice",
        )
        admin = Identity(
            platform="telegram",
            external_id="tg:user:42",
            display_name="Admin",
        )
        text = build_outcome_text(
            sender=sender,
            choice=APPROVAL_CHOICE_ALLOW_FOREVER,
            admin=admin,
        )
        assert text == "🔓 Approved forever for Alice (tg:user:99) by Admin"

    def test_allow_once_uses_green_check(self) -> None:
        sender = Identity(platform="slack", external_id="slack:user:U01")
        admin = Identity(
            platform="slack", external_id="slack:user:UAD",
            display_name="Admin",
        )
        text = build_outcome_text(
            sender=sender, choice=APPROVAL_CHOICE_ALLOW_ONCE, admin=admin,
        )
        # No display_name on sender → bare external_id (no parens).
        assert text == "✅ Approved once for slack:user:U01 by Admin"

    def test_deny_uses_red_cross(self) -> None:
        sender = Identity(
            platform="discord",
            external_id="discord:user:99",
            display_name="Bob",
        )
        admin = Identity(
            platform="discord",
            external_id="discord:user:42",
            display_name="Admin",
        )
        text = build_outcome_text(
            sender=sender, choice=APPROVAL_CHOICE_DENY, admin=admin,
        )
        assert text.startswith("🚫 Denied for Bob")

    def test_missing_admin_drops_by_suffix(self) -> None:
        """Test paths resolve approvals without a real admin Identity
        (auto-deny on TTL expiry, for instance). The ``by ...`` clause
        is optional — omitting it keeps the line clean."""
        sender = Identity(
            platform="telegram",
            external_id="tg:user:99",
            display_name="Alice",
        )
        text = build_outcome_text(
            sender=sender,
            choice=APPROVAL_CHOICE_ALLOW_ONCE,
        )
        assert text == "✅ Approved once for Alice (tg:user:99)"
        assert " by " not in text

    def test_unknown_choice_fallback(self) -> None:
        """A future broker verdict we haven't taught ``build_outcome_text``
        about renders as a visible-but-weird label rather than raising.
        The prompt edit still succeeds; operators see the raw choice
        string so the bug is easy to spot."""
        sender = Identity(platform="telegram", external_id="tg:user:99")
        text = build_outcome_text(sender=sender, choice="invented")
        assert "Resolved: invented" in text
        assert text.startswith("ℹ️")


# ---------------------------------------------------------------------------
# approval.encode_action / decode_action
# ---------------------------------------------------------------------------


class TestApprovalActionCodec:
    def test_roundtrip(self) -> None:
        for choice in sorted(APPROVAL_VALID_CHOICES):
            encoded = encode_action(choice, "abcdef1234567890")
            assert decode_action(encoded) == (choice, "abcdef1234567890")

    def test_encode_shape_matches_wire_format(self) -> None:
        """Pin the literal format so a future refactor doesn't silently
        break already-deployed buttons that bots are holding."""
        assert encode_action("allow_forever", "xyz") == (
            "approve:allow_forever:xyz"
        )

    def test_decode_rejects_wrong_prefix(self) -> None:
        assert decode_action("settings:theme:dark") is None

    def test_decode_rejects_two_part_string(self) -> None:
        assert decode_action("approve:only-two-parts") is None

    def test_decode_rejects_one_part_string(self) -> None:
        assert decode_action("approve") is None

    def test_decode_rejects_empty_approval_id(self) -> None:
        assert decode_action("approve:allow_once:") is None

    def test_decode_rejects_empty_choice(self) -> None:
        assert decode_action("approve::xyz") is None

    def test_decode_preserves_colons_inside_approval_id(self) -> None:
        """``maxsplit=2`` lets the approval_id carry future
        sub-tokens (e.g. ``xyz:v2``). Lock this behaviour in so a
        later refactor doesn't quietly split those away."""
        assert decode_action("approve:deny:abc:v2") == ("deny", "abc:v2")


# ---------------------------------------------------------------------------
# text.truncate_for_platform
# ---------------------------------------------------------------------------


class TestTruncateForPlatform:
    def test_under_cap_unchanged(self) -> None:
        assert truncate_for_platform("hello", 100) == "hello"

    def test_exactly_cap_unchanged(self) -> None:
        text = "x" * 100
        assert truncate_for_platform(text, 100) == text

    def test_over_cap_ends_with_ellipsis(self) -> None:
        result = truncate_for_platform("x" * 200, 100)
        assert len(result) == 100
        assert result.endswith("…")
        assert result[:-1] == "x" * 99

    def test_cap_of_one_produces_lone_ellipsis(self) -> None:
        """Edge case: ``cap=1`` means "one character allowed" — the
        ellipsis itself fills the slot, giving no original content."""
        assert truncate_for_platform("hello", 1) == "…"

    def test_zero_cap_returns_empty(self) -> None:
        """The ``cap <= 0`` guard protects against a foot-gun the
        inline predecessors had — ``text[: -1]`` for ``cap=0`` would
        silently produce almost the full string."""
        assert truncate_for_platform("hello", 0) == ""

    def test_negative_cap_returns_empty(self) -> None:
        assert truncate_for_platform("hello", -5) == ""


# ---------------------------------------------------------------------------
# lifecycle.BackgroundTaskRunner
# ---------------------------------------------------------------------------


def _runner(timeout: float = 5.0) -> BackgroundTaskRunner:
    return BackgroundTaskRunner(
        instance_name="test",
        platform="test",
        shutdown_timeout_s=timeout,
    )


class TestBackgroundTaskRunner:
    async def test_spawn_and_drain_happy_path(self) -> None:
        """A short-lived task completes on its own; drain just waits
        for its result with no cancel needed."""
        runner = _runner()
        completed = False

        async def task() -> None:
            nonlocal completed
            await asyncio.sleep(0)
            completed = True

        runner.spawn(task())
        await runner.drain()
        assert completed
        assert not runner.running

    async def test_drain_before_spawn_is_noop(self) -> None:
        """Tolerate ``stop`` being called on a connector that never
        actually ``start``-ed — matches existing plugin shutdown
        guards."""
        runner = _runner()
        await runner.drain()  # must not raise
        assert not runner.running

    async def test_drain_is_idempotent(self) -> None:
        """Double-drain guards against racing shutdown paths (ASGI
        lifespan + signal handler both calling ``stop``)."""
        runner = _runner()

        async def task() -> None:
            return

        runner.spawn(task())
        await runner.drain()
        await runner.drain()  # second call is a no-op, no exception

    async def test_spawn_while_running_raises(self) -> None:
        """Two consecutive ``spawn`` calls should fail loudly rather
        than silently leaking the first task — matches the plugins'
        existing ``if self._connected: return`` idiom but explicit."""
        runner = _runner()

        async def long_task() -> None:
            await asyncio.sleep(10)

        runner.spawn(long_task())
        # Build the second coroutine outside the pytest.raises block so
        # we can close it explicitly on the rejection path and avoid a
        # "coroutine was never awaited" ResourceWarning.
        extra = long_task()
        try:
            with pytest.raises(RuntimeError, match="prior task"):
                runner.spawn(extra)
        finally:
            extra.close()
            await runner.drain()

    async def test_drain_cancels_on_timeout(self) -> None:
        """A task that refuses to exit within the timeout gets the
        cancel treatment. The wrapper swallows the CancelledError so
        callers don't need to catch it in ``stop``."""
        runner = _runner(timeout=0.05)

        cancelled = asyncio.Event()

        async def stuck_task() -> None:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        runner.spawn(stuck_task())
        await runner.drain()
        assert cancelled.is_set()
        assert not runner.running

    async def test_task_exception_is_logged_not_propagated(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A crashing platform loop shouldn't bubble up through
        ``drain`` — shutdown code can't act on it usefully. We rely on
        the ``_wrap`` logging to surface the problem to operators."""
        runner = _runner()

        async def bad_task() -> None:
            raise RuntimeError("synthetic")

        with caplog.at_level(logging.ERROR):
            runner.spawn(bad_task())
            await runner.drain()  # must not raise

        # The wrap path logged it.
        assert any(
            "background task crashed" in record.message
            for record in caplog.records
        )

    async def test_task_already_done_on_drain_short_circuits(self) -> None:
        """If the task completed while the caller was doing platform-
        specific 'signal loop to exit' work, drain should notice and
        return without trying to wait_for a done task."""
        runner = _runner()

        async def quick_task() -> None:
            return

        runner.spawn(quick_task())
        # Let the event loop run the task to completion.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await runner.drain()
        assert not runner.running

    async def test_running_reflects_task_state(self) -> None:
        runner = _runner()
        assert not runner.running

        async def long_task() -> None:
            await asyncio.sleep(10)

        runner.spawn(long_task())
        assert runner.running
        await runner.drain()
        assert not runner.running
