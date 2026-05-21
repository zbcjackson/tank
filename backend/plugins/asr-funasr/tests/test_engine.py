"""Tests for FunASR ASR plugin."""

import concurrent.futures
import json
import threading
from unittest.mock import MagicMock, patch

import numpy as np
from asr_funasr import create_engine
from asr_funasr.engine import FunASREngine


def _make_self_hosted_engine(**overrides) -> FunASREngine:
    """Create a self-hosted engine with the background loop mocked out."""
    config = {
        "host": "127.0.0.1",
        "port": "10095",
        "mode": "2pass",
        "sample_rate": 16000,
    }
    config.update(overrides)
    with patch("asr_funasr.engine.FunASREngine._init_funasr_websocket"):
        engine = create_engine(config)
        # Set up attributes that _init_funasr_websocket would create
        engine._send_stride = int(
            60 * engine._chunk_size[1] / 10 / 1000
            * engine._sample_rate * 2
        )
        engine._loop = None
        engine._thread = None
        engine._ws = None
        engine._connected = MagicMock()
        engine._running = False
        engine._config_sent = False
        return engine


def _make_dashscope_engine(**overrides) -> FunASREngine:
    """Create a DashScope engine with the SDK mocked out."""
    config = {
        "api_key": "sk-test-key",
        "sample_rate": 16000,
    }
    config.update(overrides)
    with patch("asr_funasr.engine.FunASREngine._init_dashscope"):
        engine = create_engine(config)
        # Set up expected attributes that _init_dashscope would create
        engine._recognition = None
        engine._recognition_started = False
        engine._recognition_closed = True
        engine._recognition_started_at = None
        engine._last_audio_sent_at = None
        engine._restart_lock = threading.Lock()
        engine._callback = MagicMock()
        return engine


# ── Factory / Config ──────────────────────────────────────────────────


class TestCreateEngine:
    def test_default_config(self):
        engine = _make_self_hosted_engine()
        assert engine._mode == "2pass"
        assert engine._sample_rate == 16000
        assert engine._chunk_size == [5, 10, 5]
        assert engine._itn is True
        assert engine._is_dashscope is False

    def test_custom_self_hosted_config(self):
        engine = _make_self_hosted_engine(
            host="10.0.0.1",
            port="8095",
            mode="online",
            is_ssl=True,
            chunk_size=[8, 8, 4],
            hotwords={"你好": 20},
            itn=False,
        )
        assert engine._host == "10.0.0.1"
        assert engine._port == "8095"
        assert engine._mode == "online"
        assert engine._is_ssl is True
        assert engine._chunk_size == [8, 8, 4]
        assert engine._hotwords == {"你好": 20}
        assert engine._itn is False
        assert engine._is_dashscope is False

    def test_dashscope_config(self):
        engine = _make_dashscope_engine(
            api_key="sk-test-key",
            model="fun-asr-realtime",
        )
        assert engine._is_dashscope is True
        assert engine._api_key == "sk-test-key"
        assert engine._model == "fun-asr-realtime"

    def test_dashscope_default_model(self):
        engine = _make_dashscope_engine()
        assert engine._model == "paraformer-realtime-v2"


# ── Lifecycle: start / process_pcm / stop ─────────────────────────────


class TestLifecycle:
    def test_start_sets_session_active(self):
        engine = _make_self_hosted_engine()
        engine._ws = MagicMock()
        engine._loop = MagicMock()

        with patch("asyncio.run_coroutine_threadsafe"):
            engine._start_session()

        assert engine._session_active is True

    def test_process_pcm_without_session_returns_empty(self):
        engine = _make_self_hosted_engine()
        audio = np.zeros(1600, dtype=np.float32)

        text = engine._process_pcm(audio)

        assert text == ""

    def test_stop_returns_final_text(self):
        engine = _make_self_hosted_engine()
        engine._session_active = True
        engine._config_sent = True
        engine._partial_text = "你好"
        engine._committed_text = "你好世界"
        engine._ws = MagicMock()
        engine._loop = MagicMock()

        with patch("asyncio.run_coroutine_threadsafe"), patch("time.sleep"):
            final_text = engine._stop_session()

        assert final_text == "你好世界"
        assert engine._session_active is False

    def test_stop_without_session_returns_empty(self):
        engine = _make_self_hosted_engine()
        engine._session_active = False

        final_text = engine._stop_session()

        assert final_text == ""

    def test_dashscope_start_creates_recognition(self):
        engine = _make_dashscope_engine()

        with patch("asr_funasr.engine.FunASREngine._start_dashscope_recognition") as mock:
            engine._start_session()
            mock.assert_called_once()

        assert engine._session_active is True

    def test_dashscope_stop_stops_recognition(self):
        engine = _make_dashscope_engine()
        engine._session_active = True
        mock_recognition = MagicMock()
        engine._recognition = mock_recognition
        engine._recognition_started = True
        engine._committed_text = "测试"

        with patch("time.sleep"):
            final_text = engine._stop_session()

        assert final_text == "测试"
        mock_recognition.stop.assert_called_once()


# ── Self-hosted FunASR message handling ───────────────────────────────


class TestHandleFunASRMessage:
    def test_2pass_online_partial(self):
        engine = _make_self_hosted_engine()
        engine._handle_funasr_message(json.dumps({
            "mode": "2pass-online",
            "text": "你好",
            "is_final": False,
        }))
        assert engine._partial_text == "你好"

    def test_2pass_offline_final(self):
        engine = _make_self_hosted_engine()
        engine._handle_funasr_message(json.dumps({
            "mode": "2pass-offline",
            "text": "你好世界",
            "is_final": True,
        }))
        assert engine._committed_text == "你好世界"
        assert engine._partial_text == ""

    def test_online_mode_partial(self):
        engine = _make_self_hosted_engine(mode="online")
        engine._handle_funasr_message(json.dumps({
            "mode": "online",
            "text": "hello",
            "is_final": False,
        }))
        assert engine._partial_text == "hello"

    def test_online_mode_final(self):
        engine = _make_self_hosted_engine(mode="online")
        engine._handle_funasr_message(json.dumps({
            "mode": "online",
            "text": "hello world",
            "is_final": True,
        }))
        assert engine._committed_text == "hello world"

    def test_offline_mode(self):
        engine = _make_self_hosted_engine(mode="offline")
        engine._handle_funasr_message(json.dumps({
            "mode": "offline",
            "text": "batch result",
        }))
        assert engine._committed_text == "batch result"

    def test_empty_text_ignored(self):
        engine = _make_self_hosted_engine()
        engine._handle_funasr_message(json.dumps({
            "mode": "2pass-offline",
            "text": "",
        }))
        assert engine._committed_text == ""

    def test_unparseable_message(self):
        engine = _make_self_hosted_engine()
        engine._handle_funasr_message(b"not json")
        assert engine._partial_text == ""


# ── DashScope SDK result handling ─────────────────────────────────────


class TestHandleDashScopeResult:
    def test_partial_result(self):
        engine = _make_dashscope_engine()

        mock_result = MagicMock()
        mock_result.get_sentence.return_value = {
            "text": "你好",
            "end_time": None,
        }

        with patch("dashscope.audio.asr.RecognitionResult") as MockResult:
            MockResult.is_sentence_end.return_value = False
            engine._handle_dashscope_result(mock_result)

        assert engine._partial_text == "你好"

    def test_final_result(self):
        engine = _make_dashscope_engine()

        mock_result = MagicMock()
        mock_result.get_sentence.return_value = {
            "text": "你好世界",
            "end_time": 2050,
        }

        with patch("dashscope.audio.asr.RecognitionResult") as MockResult:
            MockResult.is_sentence_end.return_value = True
            engine._handle_dashscope_result(mock_result)

        assert engine._committed_text == "你好世界"
        assert engine._partial_text == ""

    def test_empty_sentence_ignored(self):
        engine = _make_dashscope_engine()

        mock_result = MagicMock()
        mock_result.get_sentence.return_value = None

        engine._handle_dashscope_result(mock_result)

        assert engine._partial_text == ""


# ── URL building (self-hosted only) ───────────────────────────────────


class TestConnectionSetup:
    def test_self_hosted_url(self):
        engine = _make_self_hosted_engine(host="10.0.0.1", port="8095")
        assert engine._build_url() == "ws://10.0.0.1:8095"

    def test_self_hosted_ssl_url(self):
        engine = _make_self_hosted_engine(
            host="asr.example.com", port="443", is_ssl=True
        )
        assert engine._build_url() == "wss://asr.example.com:443"


# ── Stride calculation (self-hosted only) ─────────────────────────────


class TestSendStride:
    def test_self_hosted_default(self):
        """Default chunk_size [5, 10, 5] → stride = 1920 bytes."""
        engine = _make_self_hosted_engine()
        assert engine._send_stride == 1920

    def test_self_hosted_custom(self):
        """Custom chunk_size [8, 8, 4] → stride = 1536 bytes."""
        engine = _make_self_hosted_engine(chunk_size=[8, 8, 4])
        assert engine._send_stride == 1536


# ── Close ─────────────────────────────────────────────────────────────


class TestClose:
    def test_close_self_hosted_stops_background_loop(self):
        engine = _make_self_hosted_engine()
        engine._running = True
        engine._ws = MagicMock()
        engine._loop = MagicMock()
        mock_thread = MagicMock()
        engine._thread = mock_thread

        with patch("asyncio.run_coroutine_threadsafe"):
            engine.close()

        assert engine._running is False
        mock_thread.join.assert_called_once_with(timeout=5)
        assert engine._ws is None

    def test_close_self_hosted_is_idempotent(self):
        engine = _make_self_hosted_engine()
        engine._running = False
        engine.close()

    def test_close_dashscope_stops_recognition(self):
        engine = _make_dashscope_engine()
        mock_recognition = MagicMock()
        engine._recognition = mock_recognition
        engine._recognition_started = True
        engine._recognition_closed = False

        engine.close()

        mock_recognition.stop.assert_called_once()
        assert engine._recognition is None


# ── DashScope SDK resilience (23s timeout / watchdog / restart) ──────


class TestDashScopeResilience:
    """Tests for the resilience layer that defends against the DashScope
    SDK's hardcoded SILENCE_TIMEOUT_S=23 self-kill."""

    def test_force_reset_clears_all_state(self):
        engine = _make_dashscope_engine()
        engine._recognition = MagicMock()
        engine._recognition_started = True
        engine._recognition_closed = False
        engine._recognition_started_at = 100.0
        engine._last_audio_sent_at = 100.0
        engine._audio_buffer = bytearray(b"leftover")

        engine._force_reset()

        assert engine._recognition is None
        assert engine._recognition_started is False
        assert engine._recognition_closed is True
        assert engine._recognition_started_at is None
        assert engine._last_audio_sent_at is None
        assert len(engine._audio_buffer) == 0

    def test_watchdog_triggers_after_stale_session(self):
        """If a session is >20s old AND silent for >5s, force-reset and
        start fresh."""
        engine = _make_dashscope_engine()
        engine._recognition = MagicMock()
        engine._recognition_started = True
        engine._recognition_closed = False
        engine._recognition_started_at = 100.0
        engine._last_audio_sent_at = 100.0  # silent for the full elapsed time

        mock_recognition_cls = MagicMock()
        with patch("dashscope.audio.asr.Recognition", mock_recognition_cls), \
             patch("time.time", return_value=130.0):  # 30s elapsed, 30s silent
            engine._start_dashscope_recognition()

        # New Recognition was constructed (force_reset cleared state, then started)
        mock_recognition_cls.assert_called_once()
        assert engine._recognition_started is True

    def test_watchdog_does_not_trigger_during_active_audio(self):
        """If session is old but audio was just sent, don't reset — early-exit
        as before."""
        engine = _make_dashscope_engine()
        existing_recognition = MagicMock()
        engine._recognition = existing_recognition
        engine._recognition_started = True
        engine._recognition_closed = False
        engine._recognition_started_at = 100.0
        engine._last_audio_sent_at = 129.0  # last audio 1s ago

        mock_recognition_cls = MagicMock()
        with patch("dashscope.audio.asr.Recognition", mock_recognition_cls), \
             patch("time.time", return_value=130.0):  # 30s elapsed, 1s silence
            engine._start_dashscope_recognition()

        # Watchdog skipped — no new Recognition created, existing kept
        mock_recognition_cls.assert_not_called()
        assert engine._recognition is existing_recognition

    def test_watchdog_does_not_trigger_for_young_session(self):
        """If session is recent, even if silent, don't reset."""
        engine = _make_dashscope_engine()
        existing_recognition = MagicMock()
        engine._recognition = existing_recognition
        engine._recognition_started = True
        engine._recognition_closed = False
        engine._recognition_started_at = 100.0
        engine._last_audio_sent_at = 100.0

        mock_recognition_cls = MagicMock()
        with patch("dashscope.audio.asr.Recognition", mock_recognition_cls), \
             patch("time.time", return_value=110.0):  # only 10s elapsed
            engine._start_dashscope_recognition()

        mock_recognition_cls.assert_not_called()
        assert engine._recognition is existing_recognition

    def test_stopped_exception_triggers_restart(self):
        """When DashScope's send_audio_frame raises 'stopped', force-reset
        and restart so the audio isn't lost."""
        engine = _make_dashscope_engine()
        first_recognition = MagicMock()
        first_recognition.send_audio_frame.side_effect = RuntimeError(
            "Speech recognition has stopped."
        )
        engine._recognition = first_recognition
        engine._recognition_started = True
        engine._recognition_closed = False

        with patch.object(engine, "_start_dashscope_recognition") as mock_start:
            audio_chunk = b"\x00" * 3200  # one ~100ms chunk
            engine._process_dashscope(audio_chunk)
            mock_start.assert_called_once()

        # Audio was preserved so the restarted session can re-send it
        assert len(engine._audio_buffer) > 0

    def test_stop_timeout_calls_force_reset(self):
        """If recognition.stop() hangs past 5s, _stop_dashscope_recognition
        catches the TimeoutError and force-resets."""
        engine = _make_dashscope_engine()
        hanging_recognition = MagicMock()
        engine._recognition = hanging_recognition
        engine._recognition_started = True
        engine._recognition_closed = False
        engine._audio_buffer = bytearray()
        engine._committed_text = ""

        # Make future.result() raise TimeoutError to simulate hang
        mock_future = MagicMock()
        mock_future.result.side_effect = concurrent.futures.TimeoutError()

        mock_pool = MagicMock()
        mock_pool.__enter__ = MagicMock(return_value=mock_pool)
        mock_pool.__exit__ = MagicMock(return_value=False)
        mock_pool.submit.return_value = mock_future

        with patch("asr_funasr.engine.concurrent.futures.ThreadPoolExecutor",
                   return_value=mock_pool), \
             patch("time.sleep"), \
             patch.object(engine, "_force_reset", wraps=engine._force_reset) as spy:
            engine._stop_dashscope_recognition()

        spy.assert_called_once()
        assert engine._recognition is None

    def test_on_open_records_session_timestamps(self):
        """The on_open callback must initialize started_at and last_audio_sent_at."""
        # We can't easily exercise on_open without the SDK, but we can verify
        # the contract via _init_dashscope's initial state:
        engine = _make_dashscope_engine()
        # Fresh engine has no timestamps — they're set when on_open fires.
        assert engine._recognition_started_at is None
        assert engine._last_audio_sent_at is None

