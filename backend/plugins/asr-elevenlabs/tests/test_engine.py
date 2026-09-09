"""Tests for the ElevenLabs realtime ASR engine.

The background thread / WebSocket is never started here: ``_start_background_loop``
is patched out and the session logic is driven directly. Where the finalize
handshake needs a socket, a fake ``_ws`` / ``_loop`` plus a patched
``run_coroutine_threadsafe`` stand in for the real connection.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from asr_elevenlabs import create_engine
from asr_elevenlabs import engine as engine_mod

CONFIG = {"api_key": "test_key", "sample_rate": 16000}


def _make_engine(**overrides):
    cfg = {**CONFIG, **overrides}
    with patch.object(engine_mod.ElevenLabsASREngine, "_start_background_loop"):
        return create_engine(cfg)


# ── message parsing ──────────────────────────────────────────────────


def test_partial_transcript_updates_partial_state():
    eng = _make_engine()
    eng._handle_message({"message_type": "partial_transcript", "text": "hello wor"})
    assert eng._partial_text == "hello wor"
    assert eng._committed_text == ""


def test_committed_transcript_sets_committed_and_clears_partial():
    eng = _make_engine()
    eng._partial_text = "hello wor"
    eng._handle_message({"message_type": "committed_transcript", "text": "hello world"})
    assert eng._committed_text == "hello world"
    assert eng._partial_text == ""


def test_committed_transcript_unblocks_stop_waiter():
    eng = _make_engine()
    eng._commit_done.clear()
    eng._handle_message({"message_type": "committed_transcript", "text": "done"})
    assert eng._commit_done.is_set()


def test_input_error_unblocks_stop_waiter():
    """A rejected commit must not hang stop() until timeout."""
    eng = _make_engine()
    eng._commit_done.clear()
    eng._handle_message({"message_type": "input_error", "message": "bad"})
    assert eng._commit_done.is_set()


# ── session lifecycle ────────────────────────────────────────────────


def test_start_requests_connection_when_disconnected():
    eng = _make_engine()
    eng._connected.clear()
    with patch.object(eng, "_request_connect") as req:
        # connected is never set, so it will time out — shrink the wait.
        with patch.object(engine_mod, "_CONNECT_TIMEOUT_S", 0.01):
            eng._start_session()
        req.assert_called_once()
    assert eng._session_active


def test_start_skips_connect_when_already_connected():
    eng = _make_engine()
    eng._connected.set()
    with patch.object(eng, "_request_connect") as req:
        eng._start_session()
        req.assert_not_called()


def test_process_pcm_without_active_session_returns_empty():
    eng = _make_engine()
    eng._session_active = False
    assert eng._process_pcm(np.zeros(160, dtype=np.float32)) == ""


def test_process_pcm_returns_current_transcript():
    eng = _make_engine()
    eng._session_active = True
    eng._partial_text = "partial"
    # No socket wired, so nothing is sent; it just reflects state.
    assert eng._process_pcm(np.zeros(160, dtype=np.float32)) == "partial"


# ── cold-start buffering ─────────────────────────────────────────────
#
# The socket connects lazily on first speech and the remote only accepts
# audio after its ``session_started`` reply. Chunks arriving before that
# moment must be buffered (not dropped) or a short first utterance is lost
# entirely — the E2E voice scenario regressed exactly this way.


def test_process_pcm_buffers_while_socket_not_ready():
    eng = _make_engine()
    eng._session_active = True
    eng._process_pcm(np.zeros(160, dtype=np.float32))
    assert len(eng._pending_audio) == 1


def test_process_pcm_buffers_until_session_started_arrives():
    """Connected socket is not enough — the remote rejects pre-session audio."""
    eng = _make_engine()
    eng._session_active = True
    _wire_fake_socket(eng)  # ws attached …
    eng._ws_session_ready = False  # … but session_started not yet received
    eng._process_pcm(np.zeros(160, dtype=np.float32))
    assert len(eng._pending_audio) == 1


def _wire_async_socket(eng):
    """Attach an AsyncMock ws (send returns awaitables) + fake loop."""
    from unittest.mock import AsyncMock

    eng._ws = AsyncMock()
    eng._loop = MagicMock()


def _noop_schedule(eng_mod):
    """run_coroutine_threadsafe that just closes the coroutine."""
    return patch.object(
        eng_mod.asyncio, "run_coroutine_threadsafe",
        side_effect=lambda coro, loop: coro.close(),
    )


def _sent_payloads(eng):
    import json as _json

    return [
        _json.loads(call.args[0]) for call in eng._ws.send.call_args_list
    ]


def test_session_started_flushes_pending_chunks_in_order():
    eng = _make_engine()
    eng._session_active = True
    _wire_async_socket(eng)
    eng._pending_audio = ["AAA=", "BBB="]

    with _noop_schedule(engine_mod):
        eng._handle_message({"message_type": "session_started", "session_id": "s1"})

    assert eng._ws_session_ready is True
    assert len(eng._pending_audio) == 0
    payloads = _sent_payloads(eng)
    assert [p["audio_base_64"] for p in payloads] == ["AAA=", "BBB="]
    assert all(p["commit"] is False for p in payloads)


def test_stop_flushes_pending_audio_before_commit():
    eng = _make_engine()
    eng._session_active = True
    _wire_async_socket(eng)
    eng._ws_session_ready = True
    eng._pending_audio = ["AAA="]
    eng._commit_done.set()

    with _noop_schedule(engine_mod):
        eng._stop_session()

    payloads = _sent_payloads(eng)
    assert len(payloads) == 2
    assert payloads[0]["audio_base_64"] == "AAA="
    assert payloads[1]["commit"] is True, "commit must be flushed last"


def test_pending_buffer_is_bounded_drop_oldest():
    eng = _make_engine()
    eng._session_active = True
    eng._pending_audio = [f"c{i}" for i in range(engine_mod._MAX_PENDING_CHUNKS + 10)]
    eng._pending_secs = 60.0
    eng._trim_pending()
    assert len(eng._pending_audio) == engine_mod._MAX_PENDING_CHUNKS
    assert eng._pending_audio[0] == "c10"
    assert eng._pending_secs == pytest.approx(59.0)  # 10 chunks × ~0.1s


# ── adaptive commit wait ─────────────────────────────────────────────


def test_commit_wait_floors_at_default():
    assert engine_mod._commit_wait_secs(0.0) == pytest.approx(
        engine_mod._FINALIZE_TIMEOUT_S
    )


def test_commit_wait_scales_with_flushed_audio():
    assert engine_mod._commit_wait_secs(2.0) == pytest.approx(3.5)


def test_commit_wait_is_capped():
    assert engine_mod._commit_wait_secs(30.0) == pytest.approx(
        engine_mod._MAX_COMMIT_WAIT_S
    )


def test_process_pcm_tracks_pending_duration():
    eng = _make_engine()
    eng._session_active = True
    eng._process_pcm(np.zeros(1600, dtype=np.float32))  # 100ms @ 16kHz
    assert eng._pending_secs == pytest.approx(0.1)


# ── finalize handshake ───────────────────────────────────────────────


def _wire_fake_socket(eng):
    """Attach a fake ws/loop so stop() takes the forced-commit path."""
    eng._ws = MagicMock()
    eng._loop = MagicMock()


def test_stop_forces_commit_and_returns_committed_text():
    eng = _make_engine()
    eng._session_active = True
    _wire_fake_socket(eng)
    eng._committed_text = "final answer"
    eng._commit_done.set()  # pretend the commit already flushed

    sent = []
    with patch.object(engine_mod.asyncio, "run_coroutine_threadsafe",
                      side_effect=lambda coro, loop: sent.append(coro)):
        result = eng._stop_session()

    assert result == "final answer"
    assert sent, "stop() should send a forced-commit chunk"
    assert not eng._session_active
    # buffers cleared for the next turn
    assert eng._committed_text == ""
    assert eng._partial_text == ""


def test_stop_falls_back_to_partial_on_commit_timeout():
    eng = _make_engine()
    eng._session_active = True
    _wire_fake_socket(eng)
    eng._partial_text = "partial only"
    eng._commit_done.clear()  # commit never lands

    with patch.object(engine_mod, "_FINALIZE_TIMEOUT_S", 0.01), \
         patch.object(engine_mod.asyncio, "run_coroutine_threadsafe"):
        result = eng._stop_session()

    assert result == "partial only"


def test_stop_without_active_session_returns_empty():
    eng = _make_engine()
    eng._session_active = False
    assert eng._stop_session() == ""


# ── factory ──────────────────────────────────────────────────────────


def test_create_engine_passes_idle_close_secs():
    with patch.object(engine_mod.ElevenLabsASREngine, "_start_background_loop"):
        eng = create_engine({**CONFIG, "idle_close_secs": 12.5})
    assert eng._idle_close_secs == 12.5


def test_create_engine_defaults_idle_close_secs():
    eng = _make_engine()
    assert eng._idle_close_secs == pytest.approx(30.0)
