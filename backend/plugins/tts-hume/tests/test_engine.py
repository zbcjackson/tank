"""Test Hume Octave TTS plugin."""

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest
from tank_contracts.tts import AudioChunk
from tts_hume import create_engine


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
    return {"api_key": "test_key", "sample_rate": 24000, **overrides}


def test_create_engine():
    assert create_engine(_config()) is not None


@pytest.mark.asyncio
async def test_generate_stream_basic():
    engine = create_engine(_config(description="warm and calm"))
    test_audio = b"\x00\x01" * 100
    audio_b64 = base64.b64encode(test_audio).decode("ascii")
    messages = [
        json.dumps({"audio": audio_b64, "is_last": False}),
        json.dumps({"audio": audio_b64, "is_last": True}),
    ]
    mock_connect, mock_ws = _mock_connect(messages)

    with patch("tts_hume.engine.websockets.connect", return_value=mock_connect):
        chunks = [c async for c in engine.generate_stream("Hello", language="en")]

    assert len(chunks) == 2
    assert isinstance(chunks[0], AudioChunk)
    assert chunks[0].sample_rate == 24000
    assert chunks[0].data == test_audio
    # description flows into the request payload
    sent = json.loads(mock_ws.send.call_args[0][0])
    assert sent["utterances"][0]["description"] == "warm and calm"


@pytest.mark.asyncio
async def test_interruption():
    engine = create_engine(_config())
    interrupted = {"v": False}
    audio_b64 = base64.b64encode(b"\x00\x01" * 100).decode("ascii")
    messages = [json.dumps({"audio": audio_b64, "is_last": False})] * 4
    mock_connect, _ = _mock_connect(messages)

    with patch("tts_hume.engine.websockets.connect", return_value=mock_connect):
        chunks = []
        async for chunk in engine.generate_stream(
            "text", language="en", is_interrupted=lambda: interrupted["v"]
        ):
            chunks.append(chunk)
            if len(chunks) == 2:
                interrupted["v"] = True

    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_voice_reference_enables_instant_mode():
    engine = create_engine(_config(voice_name="Ito"))
    audio_b64 = base64.b64encode(b"\x00\x01" * 10).decode("ascii")
    messages = [json.dumps({"audio": audio_b64, "is_last": True})]
    mock_connect, mock_ws = _mock_connect(messages)

    with patch("tts_hume.engine.websockets.connect", return_value=mock_connect):
        [c async for c in engine.generate_stream("hi", language="en")]

    sent = json.loads(mock_ws.send.call_args[0][0])
    assert sent["utterances"][0]["voice"] == {"name": "Ito"}
    assert sent["instant_mode"] is True


@pytest.mark.asyncio
async def test_error_stops_stream():
    engine = create_engine(_config())
    messages = [json.dumps({"error": True, "message": "bad"})]
    mock_connect, _ = _mock_connect(messages)

    with patch("tts_hume.engine.websockets.connect", return_value=mock_connect):
        chunks = [c async for c in engine.generate_stream("x", language="en")]

    assert chunks == []
