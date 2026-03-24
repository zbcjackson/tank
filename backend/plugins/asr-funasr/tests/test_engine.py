"""Tests for FunASR ASR plugin."""

import json

import numpy as np
from unittest.mock import patch, MagicMock

from asr_funasr import create_engine
from asr_funasr.engine import FunASREngine


def _make_engine(**overrides) -> FunASREngine:
    """Create an engine with the background loop mocked out."""
    config = {
        "host": "127.0.0.1",
        "port": "10095",
        "mode": "2pass",
        "sample_rate": 16000,
    }
    config.update(overrides)
    with patch("asr_funasr.engine.FunASREngine._start_background_loop"):
        return create_engine(config)


# ── Factory / Config ──────────────────────────────────────────────────


class TestCreateEngine:
    def test_default_config(self):
        engine = _make_engine()
        assert engine._mode == "2pass"
        assert engine._sample_rate == 16000
        assert engine._chunk_size == [5, 10, 5]
        assert engine._itn is True
        assert engine._is_dashscope is False

    def test_custom_self_hosted_config(self):
        engine = _make_engine(
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
        engine = _make_engine(
            api_key="sk-test-key",
            model="fun-asr-realtime",
        )
        assert engine._is_dashscope is True
        assert engine._api_key == "sk-test-key"
        assert engine._model == "fun-asr-realtime"
        # DashScope uses 100ms stride: 16000 * 0.1 * 2 = 3200
        assert engine._send_stride == 3200


# ── process_pcm ───────────────────────────────────────────────────────


class TestProcessPcm:
    def test_returns_partial_text(self):
        engine = _make_engine()
        engine._partial_text = "你好世界"
        engine._has_endpoint = False

        audio = np.zeros(1600, dtype=np.float32)
        text, is_endpoint = engine.process_pcm(audio)

        assert text == "你好世界"
        assert is_endpoint is False

    def test_returns_committed_text_with_endpoint(self):
        engine = _make_engine()
        engine._committed_text = "今天天气很好"
        engine._has_endpoint = True

        audio = np.zeros(1600, dtype=np.float32)
        text, is_endpoint = engine.process_pcm(audio)

        assert text == "今天天气很好"
        assert is_endpoint is True
        assert engine._committed_text == ""
        assert engine._has_endpoint is False

    def test_sends_audio_when_connected(self):
        engine = _make_engine()
        engine._config_sent = True

        mock_ws = MagicMock()
        mock_loop = MagicMock()
        engine._ws = mock_ws
        engine._loop = mock_loop

        # stride = 1920 bytes = 960 int16 samples
        audio = np.zeros(960, dtype=np.float32)

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            engine.process_pcm(audio)
            assert mock_run.called

    def test_buffers_small_chunks(self):
        engine = _make_engine()
        engine._config_sent = True
        engine._ws = MagicMock()
        engine._loop = MagicMock()

        audio = np.zeros(320, dtype=np.float32)

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            engine.process_pcm(audio)
            mock_run.assert_not_called()
            assert len(engine._audio_buffer) == 640

    def test_no_send_when_disconnected(self):
        engine = _make_engine()
        engine._ws = None

        audio = np.zeros(1600, dtype=np.float32)

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            engine.process_pcm(audio)
            mock_run.assert_not_called()

    def test_dashscope_waits_for_task_started(self):
        """DashScope: audio not sent until task-started sets _config_sent."""
        engine = _make_engine(api_key="sk-test")
        # _config_sent is False by default (set by task-started event)
        assert engine._config_sent is False

        engine._ws = MagicMock()
        engine._loop = MagicMock()

        audio = np.zeros(1600, dtype=np.float32)

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            engine.process_pcm(audio)
            mock_run.assert_not_called()


# ── Self-hosted FunASR message handling ───────────────────────────────


class TestHandleFunASRMessage:
    def test_2pass_online_partial(self):
        engine = _make_engine()
        engine._handle_server_message(json.dumps({
            "mode": "2pass-online",
            "text": "你好",
            "is_final": False,
        }))
        assert engine._partial_text == "你好"
        assert engine._has_endpoint is False

    def test_2pass_offline_final(self):
        engine = _make_engine()
        engine._handle_server_message(json.dumps({
            "mode": "2pass-offline",
            "text": "你好世界",
            "is_final": True,
        }))
        assert engine._committed_text == "你好世界"
        assert engine._has_endpoint is True
        assert engine._partial_text == ""

    def test_online_mode_partial(self):
        engine = _make_engine(mode="online")
        engine._handle_server_message(json.dumps({
            "mode": "online",
            "text": "hello",
            "is_final": False,
        }))
        assert engine._partial_text == "hello"
        assert engine._has_endpoint is False

    def test_online_mode_final(self):
        engine = _make_engine(mode="online")
        engine._handle_server_message(json.dumps({
            "mode": "online",
            "text": "hello world",
            "is_final": True,
        }))
        assert engine._committed_text == "hello world"
        assert engine._has_endpoint is True

    def test_offline_mode(self):
        engine = _make_engine(mode="offline")
        engine._handle_server_message(json.dumps({
            "mode": "offline",
            "text": "batch result",
        }))
        assert engine._committed_text == "batch result"
        assert engine._has_endpoint is True

    def test_empty_text_ignored(self):
        engine = _make_engine()
        engine._handle_server_message(json.dumps({
            "mode": "2pass-offline",
            "text": "",
        }))
        assert engine._has_endpoint is False

    def test_unparseable_message(self):
        engine = _make_engine()
        engine._handle_server_message(b"not json")
        assert engine._partial_text == ""


# ── DashScope message handling ────────────────────────────────────────


class TestHandleDashScopeMessage:
    def test_task_started(self):
        engine = _make_engine(api_key="sk-test")
        engine._handle_server_message(json.dumps({
            "header": {
                "task_id": "abc123",
                "event": "task-started",
                "attributes": {},
            },
            "payload": {},
        }))
        assert engine._config_sent is True
        assert engine._task_started.is_set()

    def test_partial_result(self):
        engine = _make_engine(api_key="sk-test")
        engine._handle_server_message(json.dumps({
            "header": {
                "task_id": "abc123",
                "event": "result-generated",
                "attributes": {},
            },
            "payload": {
                "output": {
                    "sentence": {
                        "begin_time": 170,
                        "end_time": None,
                        "text": "你好",
                        "sentence_end": False,
                    },
                },
            },
        }))
        assert engine._partial_text == "你好"
        assert engine._has_endpoint is False

    def test_final_result(self):
        engine = _make_engine(api_key="sk-test")
        engine._handle_server_message(json.dumps({
            "header": {
                "task_id": "abc123",
                "event": "result-generated",
                "attributes": {},
            },
            "payload": {
                "output": {
                    "sentence": {
                        "begin_time": 170,
                        "end_time": 2050,
                        "text": "你好世界",
                        "sentence_end": True,
                    },
                },
                "usage": {"duration": 2},
            },
        }))
        assert engine._committed_text == "你好世界"
        assert engine._has_endpoint is True
        assert engine._partial_text == ""

    def test_task_failed(self):
        engine = _make_engine(api_key="sk-test")
        # Should not raise, just log
        engine._handle_server_message(json.dumps({
            "header": {
                "task_id": "abc123",
                "event": "task-failed",
                "error_code": "CLIENT_ERROR",
                "error_message": "request timeout",
            },
            "payload": {},
        }))
        assert engine._has_endpoint is False

    def test_task_finished(self):
        engine = _make_engine(api_key="sk-test")
        engine._handle_server_message(json.dumps({
            "header": {
                "task_id": "abc123",
                "event": "task-finished",
                "attributes": {},
            },
            "payload": {"output": {}, "usage": None},
        }))
        # No state change
        assert engine._has_endpoint is False


# ── URL / header building ─────────────────────────────────────────────


class TestConnectionSetup:
    def test_self_hosted_url(self):
        engine = _make_engine(host="10.0.0.1", port="8095")
        assert engine._build_url() == "ws://10.0.0.1:8095"

    def test_self_hosted_ssl_url(self):
        engine = _make_engine(host="asr.example.com", port="443", is_ssl=True)
        assert engine._build_url() == "wss://asr.example.com:443"

    def test_dashscope_default_url(self):
        engine = _make_engine(api_key="sk-test")
        assert engine._build_url() == "wss://dashscope.aliyuncs.com/api-ws/v1/inference"

    def test_dashscope_custom_url(self):
        engine = _make_engine(
            api_key="sk-test",
            dashscope_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference",
        )
        assert engine._build_url() == "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"

    def test_self_hosted_no_headers(self):
        engine = _make_engine()
        assert engine._build_headers() == {}

    def test_dashscope_auth_header(self):
        engine = _make_engine(api_key="sk-my-key")
        headers = engine._build_headers()
        assert headers["Authorization"] == "Bearer sk-my-key"


# ── Reset ─────────────────────────────────────────────────────────────


class TestReset:
    def test_clears_transcript_state(self):
        engine = _make_engine()
        engine._partial_text = "partial"
        engine._committed_text = "committed"
        engine._has_endpoint = True

        engine.reset()

        assert engine._partial_text == ""
        assert engine._committed_text == ""
        assert engine._has_endpoint is False

    def test_self_hosted_sends_is_speaking_false(self):
        engine = _make_engine()
        engine._audio_buffer = bytearray(b"\x00" * 100)
        engine._ws = MagicMock()
        engine._loop = MagicMock()

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            engine.reset()
            # remaining audio + EOS
            assert mock_run.call_count == 2

    def test_dashscope_sends_finish_task(self):
        engine = _make_engine(api_key="sk-test")
        engine._task_id = "test-task-123"
        engine._audio_buffer = bytearray()
        engine._ws = MagicMock()
        engine._loop = MagicMock()

        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            engine.reset()
            # Only finish-task (no remaining audio)
            assert mock_run.call_count == 1


# ── Stride calculation ────────────────────────────────────────────────


class TestSendStride:
    def test_self_hosted_default(self):
        """Default chunk_size [5, 10, 5] → stride = 1920 bytes."""
        engine = _make_engine()
        assert engine._send_stride == 1920

    def test_self_hosted_custom(self):
        """Custom chunk_size [8, 8, 4] → stride = 1536 bytes."""
        engine = _make_engine(chunk_size=[8, 8, 4])
        assert engine._send_stride == 1536

    def test_dashscope_100ms_stride(self):
        """DashScope uses 100ms chunks: 16000 * 0.1 * 2 = 3200."""
        engine = _make_engine(api_key="sk-test")
        assert engine._send_stride == 3200


# ── Close ─────────────────────────────────────────────────────────────


class TestClose:
    def test_close_stops_background_loop(self):
        engine = _make_engine()
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

    def test_close_is_idempotent(self):
        engine = _make_engine()
        engine._running = False
        engine.close()
