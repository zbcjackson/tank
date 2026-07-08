"""Test Cartesia TTS plugin."""

import base64
from unittest.mock import AsyncMock, patch

import pytest
from tank_contracts.tts import AudioChunk
from tts_cartesia import create_engine


async def _async_iter(items):
    for item in items:
        yield item


def _mock_connect(messages):
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.__aiter__ = lambda self: _async_iter(messages).__aiter__()
    mock_connect = AsyncMock()
    mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_connect.__aexit__ = AsyncMock(return_value=None)
    return mock_connect, mock_ws


def _config(**overrides):
    return {
        "api_key": "test_key",
        "default_voice": "voice-uuid",
        "sample_rate": 24000,
        **overrides,
    }


def test_create_engine():
    assert create_engine(_config()) is not None


def test_voice_selection():
    engine = create_engine(_config(voices={"en": "en-voice", "zh": "zh-voice"}))
    assert engine._voice_for_language("en") == "en-voice"
    assert engine._voice_for_language("zh-CN") == "zh-voice"
    assert engine._voice_for_language("auto") == "voice-uuid"


@pytest.mark.asyncio
async def test_generate_stream_basic():
    engine = create_engine(_config())
    test_audio = b"\x00\x01" * 100
    audio_b64 = base64.b64encode(test_audio).decode("ascii")
    messages = [
        f'{{"type": "chunk", "data": "{audio_b64}"}}',
        '{"type": "done"}',
    ]
    mock_connect, mock_ws = _mock_connect(messages)

    with patch("tts_cartesia.engine.websockets.connect", return_value=mock_connect):
        chunks = [c async for c in engine.generate_stream("Hello", language="en")]

    assert len(chunks) == 1
    assert isinstance(chunks[0], AudioChunk)
    assert chunks[0].sample_rate == 24000
    assert chunks[0].data == test_audio
    # Request payload sent once
    assert mock_ws.send.call_count == 1


@pytest.mark.asyncio
async def test_interruption():
    engine = create_engine(_config())
    interrupted = {"v": False}
    test_audio = b"\x00\x01" * 100
    audio_b64 = base64.b64encode(test_audio).decode("ascii")
    messages = [f'{{"type": "chunk", "data": "{audio_b64}"}}'] * 4
    mock_connect, _ = _mock_connect(messages)

    with patch("tts_cartesia.engine.websockets.connect", return_value=mock_connect):
        chunks = []
        async for chunk in engine.generate_stream(
            "text", language="en", is_interrupted=lambda: interrupted["v"]
        ):
            chunks.append(chunk)
            if len(chunks) == 2:
                interrupted["v"] = True

    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_error_message_stops_stream():
    engine = create_engine(_config())
    messages = ['{"type": "error", "title": "boom", "message": "bad"}']
    mock_connect, _ = _mock_connect(messages)

    with patch("tts_cartesia.engine.websockets.connect", return_value=mock_connect):
        chunks = [c async for c in engine.generate_stream("x", language="en")]

    assert chunks == []
