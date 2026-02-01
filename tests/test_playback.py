"""Tests for audio output playback."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from src.voice_assistant.audio.output.types import AudioChunk
from src.voice_assistant.audio.output.playback import play_stream


@pytest.mark.asyncio
async def test_play_stream_writes_chunks_to_sounddevice():
    """play_stream consumes async chunk stream and writes PCM to sounddevice."""
    # PCM int16 mono, 24000 Hz: 0.1s = 2400 samples = 4800 bytes
    sample_rate = 24000
    n_samples = 2400
    pcm_bytes = np.zeros(n_samples, dtype=np.int16).tobytes()
    chunks = [
        AudioChunk(data=pcm_bytes, sample_rate=sample_rate, channels=1),
    ]

    async def chunk_iter():
        for c in chunks:
            yield c

    mock_stream = MagicMock()

    with patch("src.voice_assistant.audio.output.playback.sd.OutputStream", return_value=mock_stream):
        await play_stream(chunk_iter(), is_interrupted=lambda: False)

    mock_stream.start.assert_called_once()
    mock_stream.write.assert_called_once()
    written = mock_stream.write.call_args[0][0]
    assert written.dtype == np.int16
    assert len(written) == n_samples
    mock_stream.stop.assert_called()
    mock_stream.close.assert_called()


@pytest.mark.asyncio
async def test_play_stream_stops_when_interrupted():
    """play_stream stops consuming when is_interrupted returns True."""
    pcm_bytes = np.zeros(480, dtype=np.int16).tobytes()
    chunk = AudioChunk(data=pcm_bytes, sample_rate=24000, channels=1)
    call_count = [0]

    async def chunk_iter():
        yield chunk
        yield chunk

    def is_interrupted():
        call_count[0] += 1
        return call_count[0] > 1

    mock_stream = MagicMock()
    with patch("src.voice_assistant.audio.output.playback.sd.OutputStream", return_value=mock_stream):
        await play_stream(chunk_iter(), is_interrupted=is_interrupted)

    assert mock_stream.write.call_count == 1
