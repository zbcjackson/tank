"""Regression test for Phase 22's SDK-noise logger config.

The four connector SDKs (aiogram, slack_bolt, discord.py, lark-oapi)
each emit transient-network noise at WARNING/ERROR level under
flaky-network conditions. Tank's tmux session log was getting
drowned by that noise to the point operators learned to ignore
those levels — exactly the signal-erosion failure mode this config
prevents.

The fix bumps each noisy logger to a level high enough to silence
the routine retries while leaving genuine catastrophic failures
visible. This test pins those levels so a future refactor doesn't
silently regress the cleanup.

The cleanup lives in :mod:`tank_backend.api.server` so the levels
get applied as a side effect of importing the API server module —
matches where ``logging.basicConfig`` already lives.
"""

from __future__ import annotations

import logging


def test_aiogram_dispatcher_silenced_to_critical() -> None:
    """aiogram emits one ERROR + one WARNING per retry on transient
    Telegram API failures. Bump to CRITICAL — the retry loop itself
    recovers; only an escalation past the retry budget matters."""
    # Trigger the server-import side effect that applies the config.
    import tank_backend.api.server  # noqa: F401

    assert logging.getLogger("aiogram.dispatcher").level == logging.CRITICAL


def test_slack_bolt_silenced_to_critical() -> None:
    """slack_bolt logs ERROR on every WebSocket reconnect (which
    happens routinely under flaky networks). Bumping to CRITICAL
    removes the false-alarm pattern."""
    import tank_backend.api.server  # noqa: F401

    assert (
        logging.getLogger("slack_bolt.AsyncApp").level == logging.CRITICAL
    )


def test_discord_client_silenced_to_error() -> None:
    """discord.py emits ``PyNaCl is not installed`` / ``davey is
    not installed`` WARNINGs on every connect. Tank doesn't need
    those libs (voice rooms are unsupported); the warnings were
    never actionable."""
    import tank_backend.api.server  # noqa: F401

    assert logging.getLogger("discord.client").level == logging.ERROR


def test_discord_gateway_silenced_to_warning() -> None:
    """discord.gateway emits heartbeat-level INFO that's useful
    only while debugging the gateway. Bumping to WARNING keeps
    real gateway issues observable without the chatter."""
    import tank_backend.api.server  # noqa: F401

    assert logging.getLogger("discord.gateway").level == logging.WARNING


def test_critical_events_still_surface_for_silenced_loggers(
    caplog: object,
) -> None:
    """Defence in depth: a logger silenced to CRITICAL should still
    emit on ``logger.critical``. Confirms we're capping floor noise
    rather than dropping the logger entirely."""
    import logging as logging_mod

    import tank_backend.api.server  # noqa: F401

    aiogram_logger = logging_mod.getLogger("aiogram.dispatcher")

    # Sanity: WARNING/ERROR get filtered.
    with caplog.at_level(logging_mod.WARNING):  # type: ignore[attr-defined]
        aiogram_logger.warning("synthetic retry warning")
        aiogram_logger.error("synthetic retry error")
    warn_lines = [
        r for r in caplog.records  # type: ignore[attr-defined]
        if r.name == "aiogram.dispatcher"
    ]
    assert warn_lines == []

    # CRITICAL still gets through.
    with caplog.at_level(logging_mod.CRITICAL):  # type: ignore[attr-defined]
        aiogram_logger.critical("synthetic catastrophic event")
    crit_lines = [
        r for r in caplog.records  # type: ignore[attr-defined]
        if r.name == "aiogram.dispatcher" and r.levelno == logging_mod.CRITICAL
    ]
    assert len(crit_lines) == 1
    assert "catastrophic" in crit_lines[0].message
