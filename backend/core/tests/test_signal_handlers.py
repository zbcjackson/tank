"""Tests for WebSocket signal handlers (api/signal_handlers.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.api.schemas import MessageType, WebsocketMessage
from tank_backend.api.signal_handlers import DisconnectSignal, dispatch


def _msg(content: str) -> WebsocketMessage:
    return WebsocketMessage(type=MessageType.SIGNAL, content=content)


async def test_unknown_signal_returns_false():
    assistant = MagicMock()
    send_fn = AsyncMock()
    handled = await dispatch(
        "not_a_real_signal", assistant, _msg("not_a_real_signal"), "sess", send_fn,
    )
    assert handled is False


async def test_interrupt_calls_assistant_interrupt():
    assistant = MagicMock()
    send_fn = AsyncMock()
    handled = await dispatch("interrupt", assistant, _msg("interrupt"), "sess", send_fn)
    assert handled is True
    assistant.interrupt.assert_called_once()


async def test_end_of_utterance_calls_assistant_end_utterance():
    assistant = MagicMock()
    send_fn = AsyncMock()
    handled = await dispatch(
        "end_of_utterance", assistant, _msg("end_of_utterance"), "sess", send_fn,
    )
    assert handled is True
    assistant.end_utterance.assert_called_once()


async def test_idle_is_logged_only():
    """Existing handler: should not call any assistant method, just log."""
    assistant = MagicMock()
    send_fn = AsyncMock()
    handled = await dispatch("idle", assistant, _msg("idle"), "sess", send_fn)
    assert handled is True
    assistant.interrupt.assert_not_called()
    assistant.end_utterance.assert_not_called()


async def test_disconnect_raises_disconnect_signal():
    assistant = MagicMock()
    send_fn = AsyncMock()
    with pytest.raises(DisconnectSignal):
        await dispatch("disconnect", assistant, _msg("disconnect"), "sess", send_fn)
