"""Test ElevenLabs TTS plugin."""

import base64

import pytest
from unittest.mock import AsyncMock, patch
from tts_elevenlabs import create_engine
from tank_contracts.tts import AudioChunk


async def _async_iter(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item


def test_create_engine():
    """Test plugin factory function."""
    config = {
        "api_key": "test_key",
        "voice_id": "test_voice",
    }
    engine = create_engine(config)
    assert engine is not None


@pytest.mark.asyncio
async def test_generate_stream_basic():
    """Test TTS generation produces audio chunks."""
    config = {
        "api_key": "test_key",
        "voice_id": "test_voice",
        "model_id": "eleven_flash_v2_5",
        "sample_rate": 24000,
    }
    engine = create_engine(config)

    test_audio = b"\x00\x01" * 100
    audio_b64 = base64.b64encode(test_audio).decode("ascii")

    messages = [
        f'{{"audio": "{audio_b64}", "isFinal": false}}',
        f'{{"audio": "{audio_b64}", "isFinal": true}}',
    ]

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.__aiter__ = lambda self: _async_iter(messages).__aiter__()

    mock_connect = AsyncMock()
    mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_connect.__aexit__ = AsyncMock(return_value=None)

    with patch("tts_elevenlabs.engine.websockets.connect", return_value=mock_connect):
        chunks = []
        async for chunk in engine.generate_stream("Hello", language="en"):
            chunks.append(chunk)
            assert isinstance(chunk, AudioChunk)
            assert chunk.sample_rate == 24000
            assert chunk.channels == 1
            assert len(chunk.data) > 0

        assert len(chunks) == 2
        # Verify 3 sends: init, text+flush, close
        assert mock_ws.send.call_count == 3


@pytest.mark.asyncio
async def test_interruption():
    """Test that is_interrupted callback stops generation."""
    config = {
        "api_key": "test_key",
        "voice_id": "test_voice",
    }
    engine = create_engine(config)

    interrupted = False

    def is_interrupted():
        return interrupted

    test_audio = b"\x00\x01" * 100
    audio_b64 = base64.b64encode(test_audio).decode("ascii")

    messages = [
        f'{{"audio": "{audio_b64}", "isFinal": false}}',
        f'{{"audio": "{audio_b64}", "isFinal": false}}',
        f'{{"audio": "{audio_b64}", "isFinal": false}}',
        f'{{"audio": "{audio_b64}", "isFinal": true}}',
    ]

    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.__aiter__ = lambda self: _async_iter(messages).__aiter__()

    mock_connect = AsyncMock()
    mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_connect.__aexit__ = AsyncMock(return_value=None)

    with patch("tts_elevenlabs.engine.websockets.connect", return_value=mock_connect):
        chunks = []
        async for chunk in engine.generate_stream(
            "Long text...",
            language="en",
            is_interrupted=is_interrupted,
        ):
            chunks.append(chunk)
            if len(chunks) == 2:
                interrupted = True

        assert len(chunks) == 2


@pytest.mark.asyncio
async def test_voice_selection():
    """Test that voice is selected based on language."""
    config = {
        "api_key": "test_key",
        "voice_id": "en_voice",
        "voice_id_zh": "zh_voice",
    }
    engine = create_engine(config)

    assert engine._voice_for_language("en") == "en_voice"
    assert engine._voice_for_language("english") == "en_voice"
    assert engine._voice_for_language("zh") == "zh_voice"
    assert engine._voice_for_language("chinese") == "zh_voice"
