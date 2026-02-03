"""Tests for TTSWorker and PlaybackWorker (audio output)."""

import asyncio
import queue
from unittest.mock import MagicMock

from src.voice_assistant.audio.output.tts_worker import TTSWorker
from src.voice_assistant.audio.output.types import AudioChunk
from src.voice_assistant.core.events import AudioOutputRequest
from src.voice_assistant.core.shutdown import GracefulShutdown


def test_tts_worker_handle_puts_chunks_and_none_to_queue():
    """TTSWorker.handle gets request, calls TTS generate_stream, puts chunks and None to queue."""
    shutdown = GracefulShutdown()
    audio_output_queue = queue.Queue()
    audio_chunk_queue = queue.Queue()
    mock_engine = MagicMock()
    pcm_bytes = b"\x00\x01" * 100
    chunk = AudioChunk(data=pcm_bytes, sample_rate=24000, channels=1)

    async def mock_stream(*args, **kwargs):
        yield chunk

    mock_engine.generate_stream = MagicMock(side_effect=mock_stream)

    worker = TTSWorker(
        name="TTSThread",
        stop_signal=shutdown,
        input_queue=audio_output_queue,
        audio_chunk_queue=audio_chunk_queue,
        tts_engine=mock_engine,
    )
    worker._loop = asyncio.new_event_loop()
    asyncio.set_event_loop(worker._loop)

    req = AudioOutputRequest(content="hello", language="en")
    worker.handle(req)

    mock_engine.generate_stream.assert_called_once()
    call_kw = mock_engine.generate_stream.call_args[1]
    assert call_kw["language"] == "en"
    assert call_kw["voice"] is None
    assert call_kw["is_interrupted"] is None
    # Queue should have one chunk then None
    assert audio_chunk_queue.get() == chunk
    assert audio_chunk_queue.get() is None
