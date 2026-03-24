"""Unit tests for DashScope CosyVoice client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from tank_contracts.tts import AudioChunk
from tts_cosyvoice import CosyVoiceTTSEngine, create_engine
from tts_cosyvoice.dashscope_client import (
    CHANNELS,
    DashScopeClient,
    DashScopeError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task_started_msg(task_id: str) -> str:
    return json.dumps({
        "header": {"task_id": task_id, "event": "task-started", "attributes": {}},
        "payload": {},
    })


def _task_finished_msg(task_id: str) -> str:
    return json.dumps({
        "header": {"task_id": task_id, "event": "task-finished", "attributes": {}},
        "payload": {"output": {}, "usage": {"characters": 10}},
    })


def _task_failed_msg(task_id: str, code: str = "InvalidParam", message: str = "bad") -> str:
    return json.dumps({
        "header": {
            "task_id": task_id,
            "event": "task-failed",
            "error_code": code,
            "error_message": message,
        },
        "payload": {},
    })


def _sentence_synthesis_msg(task_id: str) -> str:
    return json.dumps({
        "header": {"task_id": task_id, "event": "result-generated"},
        "payload": {"output": {"type": "sentence-synthesis"}},
    })


def _fake_pcm(n_bytes: int = 4096) -> bytes:
    return bytes(range(256)) * (n_bytes // 256) + bytes(range(n_bytes % 256))


async def _collect_chunks(engine, text, **kwargs) -> list[AudioChunk]:
    chunks = []
    async for chunk in engine.generate_stream(text, **kwargs):
        chunks.append(chunk)
    return chunks


def _make_mock_ws(messages: list[str | bytes]):
    """Create a mock WebSocket that yields the given messages.

    Also records sent messages for assertion.
    """
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()

    async def async_iter():
        for msg in messages:
            yield msg

    mock_ws.__aiter__ = lambda self: async_iter()
    mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ws.__aexit__ = AsyncMock(return_value=False)
    return mock_ws


# ---------------------------------------------------------------------------
# Factory / config
# ---------------------------------------------------------------------------


def test_create_engine_dashscope(dashscope_config):
    """create_engine with provider=dashscope creates DashScope-backed engine."""
    engine = create_engine(dashscope_config)
    assert isinstance(engine, CosyVoiceTTSEngine)
    assert engine._provider == "dashscope"
    assert engine._dashscope is not None


def test_create_engine_local_is_default():
    """provider defaults to 'local' when not specified."""
    engine = create_engine({})
    assert engine._provider == "local"
    assert engine._dashscope is None


# ---------------------------------------------------------------------------
# DashScopeClient init
# ---------------------------------------------------------------------------


def test_client_region_intl():
    """intl region uses Singapore WebSocket URL."""
    client = DashScopeClient({
        "dashscope_api_key": "key",
        "dashscope_region": "intl",
    })
    assert "intl" in client._ws_url


def test_client_region_cn():
    """cn region uses Beijing WebSocket URL."""
    client = DashScopeClient({
        "dashscope_api_key": "key",
        "dashscope_region": "cn",
    })
    assert "intl" not in client._ws_url
    assert "dashscope.aliyuncs.com" in client._ws_url


def test_client_defaults():
    """Default model and voice are set when not specified."""
    client = DashScopeClient({"dashscope_api_key": "key"})
    assert client._model == "cosyvoice-v3-flash"
    assert client._voice_en == "longanyang"


# ---------------------------------------------------------------------------
# Voice selection
# ---------------------------------------------------------------------------


def test_voice_for_chinese():
    client = DashScopeClient({
        "dashscope_api_key": "key",
        "dashscope_voice_en": "en_voice",
        "dashscope_voice_zh": "zh_voice",
    })
    assert client.voice_for_language("zh") == "zh_voice"
    assert client.voice_for_language("zh-CN") == "zh_voice"
    assert client.voice_for_language("chinese") == "zh_voice"


def test_voice_for_english():
    client = DashScopeClient({
        "dashscope_api_key": "key",
        "dashscope_voice_en": "en_voice",
        "dashscope_voice_zh": "zh_voice",
    })
    assert client.voice_for_language("en") == "en_voice"
    assert client.voice_for_language("auto") == "en_voice"


# ---------------------------------------------------------------------------
# Streaming — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_yields_pcm_chunks(dashscope_config):
    """Binary frames from WebSocket become AudioChunk yields."""
    pcm_data = _fake_pcm(2048)

    # Simulate: task-started, sentence-synthesis JSON, binary audio, task-finished
    ws_messages = [
        _task_started_msg("tid"),
        _sentence_synthesis_msg("tid"),
        pcm_data,
        _task_finished_msg("tid"),
    ]
    mock_ws = _make_mock_ws(ws_messages)

    with patch("tts_cosyvoice.dashscope_client.websockets.connect", return_value=mock_ws):
        with patch("tts_cosyvoice.dashscope_client.uuid.uuid4", return_value="tid"):
            client = DashScopeClient(dashscope_config)
            chunks = []
            async for chunk in client.stream("Hello", language="en"):
                chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].data == pcm_data
    assert chunks[0].sample_rate == 22050
    assert chunks[0].channels == CHANNELS


@pytest.mark.asyncio
async def test_stream_multiple_binary_frames(dashscope_config):
    """Multiple binary frames are yielded as separate AudioChunks."""
    pcm1 = _fake_pcm(1024)
    pcm2 = _fake_pcm(512)

    ws_messages = [
        _task_started_msg("tid"),
        pcm1,
        pcm2,
        _task_finished_msg("tid"),
    ]
    mock_ws = _make_mock_ws(ws_messages)

    with patch("tts_cosyvoice.dashscope_client.websockets.connect", return_value=mock_ws):
        with patch("tts_cosyvoice.dashscope_client.uuid.uuid4", return_value="tid"):
            client = DashScopeClient(dashscope_config)
            chunks = []
            async for chunk in client.stream("Hello", language="en"):
                chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].data == pcm1
    assert chunks[1].data == pcm2


@pytest.mark.asyncio
async def test_stream_sends_correct_messages(dashscope_config):
    """Verify the 3-message protocol: run-task, continue-task, finish-task."""
    ws_messages = [
        _task_started_msg("tid"),
        _task_finished_msg("tid"),
    ]
    mock_ws = _make_mock_ws(ws_messages)

    with patch("tts_cosyvoice.dashscope_client.websockets.connect", return_value=mock_ws):
        with patch("tts_cosyvoice.dashscope_client.uuid.uuid4", return_value="tid"):
            client = DashScopeClient(dashscope_config)
            async for _ in client.stream("Test text", language="en"):
                pass

    assert mock_ws.send.call_count == 3
    sent = [json.loads(call.args[0]) for call in mock_ws.send.call_args_list]

    assert sent[0]["header"]["action"] == "run-task"
    assert sent[0]["payload"]["model"] == "cosyvoice-v3-flash"
    assert sent[0]["payload"]["parameters"]["voice"] == "longanyang"
    assert sent[0]["payload"]["parameters"]["format"] == "pcm"

    assert sent[1]["header"]["action"] == "continue-task"
    assert sent[1]["payload"]["input"]["text"] == "Test text"

    assert sent[2]["header"]["action"] == "finish-task"


@pytest.mark.asyncio
async def test_stream_uses_chinese_voice(dashscope_config):
    """Chinese language selects the Chinese voice."""
    ws_messages = [
        _task_started_msg("tid"),
        _task_finished_msg("tid"),
    ]
    mock_ws = _make_mock_ws(ws_messages)

    with patch("tts_cosyvoice.dashscope_client.websockets.connect", return_value=mock_ws):
        with patch("tts_cosyvoice.dashscope_client.uuid.uuid4", return_value="tid"):
            client = DashScopeClient(dashscope_config)
            async for _ in client.stream("你好", language="zh-CN"):
                pass

    sent_run = json.loads(mock_ws.send.call_args_list[0].args[0])
    assert sent_run["payload"]["parameters"]["voice"] == "longxiaochun_v2"


@pytest.mark.asyncio
async def test_stream_explicit_voice_overrides(dashscope_config):
    """Explicit voice parameter overrides language-based selection."""
    ws_messages = [
        _task_started_msg("tid"),
        _task_finished_msg("tid"),
    ]
    mock_ws = _make_mock_ws(ws_messages)

    with patch("tts_cosyvoice.dashscope_client.websockets.connect", return_value=mock_ws):
        with patch("tts_cosyvoice.dashscope_client.uuid.uuid4", return_value="tid"):
            client = DashScopeClient(dashscope_config)
            async for _ in client.stream("Hi", language="en", voice="custom_voice"):
                pass

    sent_run = json.loads(mock_ws.send.call_args_list[0].args[0])
    assert sent_run["payload"]["parameters"]["voice"] == "custom_voice"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_failed_raises(dashscope_config):
    """task-failed event raises DashScopeError."""
    ws_messages = [
        _task_started_msg("tid"),
        _task_failed_msg("tid", "InvalidVoice", "Voice not found"),
    ]
    mock_ws = _make_mock_ws(ws_messages)

    with patch("tts_cosyvoice.dashscope_client.websockets.connect", return_value=mock_ws):
        with patch("tts_cosyvoice.dashscope_client.uuid.uuid4", return_value="tid"):
            client = DashScopeClient(dashscope_config)
            with pytest.raises(DashScopeError, match="InvalidVoice"):
                async for _ in client.stream("Hello", language="en"):
                    pass


@pytest.mark.asyncio
async def test_task_failed_before_started(dashscope_config):
    """task-failed during _expect_event raises DashScopeError."""
    ws_messages = [
        _task_failed_msg("tid", "AuthFailed", "Invalid API key"),
    ]
    mock_ws = _make_mock_ws(ws_messages)

    with patch("tts_cosyvoice.dashscope_client.websockets.connect", return_value=mock_ws):
        with patch("tts_cosyvoice.dashscope_client.uuid.uuid4", return_value="tid"):
            client = DashScopeClient(dashscope_config)
            with pytest.raises(DashScopeError, match="AuthFailed"):
                async for _ in client.stream("Hello", language="en"):
                    pass


# ---------------------------------------------------------------------------
# Interruption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interruption_stops_stream(dashscope_config):
    """is_interrupted callback stops yielding chunks."""
    pcm1 = _fake_pcm(1024)
    pcm2 = _fake_pcm(1024)
    pcm3 = _fake_pcm(1024)

    ws_messages = [
        _task_started_msg("tid"),
        pcm1, pcm2, pcm3,
        _task_finished_msg("tid"),
    ]
    mock_ws = _make_mock_ws(ws_messages)

    call_count = 0

    def is_interrupted():
        return call_count >= 2

    with patch("tts_cosyvoice.dashscope_client.websockets.connect", return_value=mock_ws):
        with patch("tts_cosyvoice.dashscope_client.uuid.uuid4", return_value="tid"):
            client = DashScopeClient(dashscope_config)
            chunks = []
            async for chunk in client.stream(
                "Long text", language="en", is_interrupted=is_interrupted
            ):
                chunks.append(chunk)
                call_count += 1

    assert 1 <= len(chunks) <= 2


# ---------------------------------------------------------------------------
# Engine integration (provider=dashscope dispatches to DashScopeClient)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_dispatches_to_dashscope(dashscope_config):
    """Engine with provider=dashscope delegates to DashScopeClient.stream()."""
    pcm = _fake_pcm(512)
    ws_messages = [
        _task_started_msg("tid"),
        pcm,
        _task_finished_msg("tid"),
    ]
    mock_ws = _make_mock_ws(ws_messages)

    with patch("tts_cosyvoice.dashscope_client.websockets.connect", return_value=mock_ws):
        with patch("tts_cosyvoice.dashscope_client.uuid.uuid4", return_value="tid"):
            engine = create_engine(dashscope_config)
            chunks = await _collect_chunks(engine, "Hello", language="en")

    assert len(chunks) == 1
    assert chunks[0].data == pcm
    assert chunks[0].sample_rate == 22050
