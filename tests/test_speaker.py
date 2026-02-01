"""Tests for SpeakerHandler (audio output queue consumer)."""

import asyncio
import queue
from unittest.mock import AsyncMock, MagicMock, patch

from src.voice_assistant.audio.output.speaker import SpeakerHandler
from src.voice_assistant.audio.output.types import AudioChunk
from src.voice_assistant.core.events import AudioOutputRequest
from src.voice_assistant.core.shutdown import GracefulShutdown


def test_speaker_handle_calls_tts_and_playback():
    """SpeakerHandler.handle gets request, calls TTS generate_stream and play_stream."""
    shutdown = GracefulShutdown()
    audio_queue = queue.Queue()
    mock_engine = MagicMock()
    pcm_bytes = b"\x00\x01" * 100
    chunk = AudioChunk(data=pcm_bytes, sample_rate=24000, channels=1)

    async def mock_stream(*args, **kwargs):
        yield chunk

    mock_engine.generate_stream = MagicMock(side_effect=mock_stream)

    play_called = []

    async def mock_play(chunk_stream, is_interrupted):
        play_called.append(True)
        async for _ in chunk_stream:
            if is_interrupted():
                break
            pass

    handler = SpeakerHandler(
        shutdown_signal=shutdown,
        audio_output_queue=audio_queue,
        tts_engine=mock_engine,
    )
    handler._loop = asyncio.new_event_loop()
    asyncio.set_event_loop(handler._loop)

    with patch("src.voice_assistant.audio.output.speaker.play_stream", side_effect=mock_play):
        req = AudioOutputRequest(content="hello", language="en")
        handler.handle(req)

    mock_engine.generate_stream.assert_called_once()
    call_kw = mock_engine.generate_stream.call_args[1]
    assert call_kw["language"] == "en"
    assert call_kw["voice"] is None
    assert play_called == [True]
