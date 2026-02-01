"""Tests for audio output playback."""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from src.voice_assistant.audio.output.types import AudioChunk
from src.voice_assistant.audio.output.playback import (
    play_stream,
    FADE_DURATION_MS,
)


def _n_fade(sample_rate: int) -> int:
    return int(sample_rate * FADE_DURATION_MS / 1000)


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
    """play_stream stops when is_interrupted returns True; with one-chunk buffer no write yet."""
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

    # Buffer holds first chunk; we break when processing second, so nothing written yet
    assert mock_stream.write.call_count == 0


@pytest.mark.asyncio
async def test_play_stream_applies_fade_in_and_fade_out_on_single_chunk():
    """Single chunk is written once with fade-in on first samples and fade-out on last."""
    sample_rate = 24000
    n_samples = 2400
    # Non-zero so we can see fade: first/last samples get ramped
    pcm = np.full(n_samples, 1000, dtype=np.int16)
    chunks = [AudioChunk(data=pcm.tobytes(), sample_rate=sample_rate, channels=1)]

    async def chunk_iter():
        for c in chunks:
            yield c

    mock_stream = MagicMock()
    with patch("src.voice_assistant.audio.output.playback.sd.OutputStream", return_value=mock_stream):
        await play_stream(chunk_iter(), is_interrupted=lambda: False)

    mock_stream.write.assert_called_once()
    written = np.frombuffer(mock_stream.write.call_args[0][0].tobytes(), dtype=np.int16)
    n_fade = _n_fade(sample_rate)
    assert written[0] == 0
    assert written[n_fade - 1] == 1000
    assert written[-n_fade] == 1000
    assert written[-1] == 0


@pytest.mark.asyncio
async def test_play_stream_applies_fade_out_on_last_chunk_when_stream_ends():
    """When stream ends normally, last chunk is written with fade-out on last samples."""
    sample_rate = 24000
    n = 600
    pcm = np.full(n, 500, dtype=np.int16)
    chunks = [
        AudioChunk(data=pcm.tobytes(), sample_rate=sample_rate, channels=1),
        AudioChunk(data=pcm.tobytes(), sample_rate=sample_rate, channels=1),
    ]

    async def chunk_iter():
        for c in chunks:
            yield c

    mock_stream = MagicMock()
    with patch("src.voice_assistant.audio.output.playback.sd.OutputStream", return_value=mock_stream):
        await play_stream(chunk_iter(), is_interrupted=lambda: False)

    assert mock_stream.write.call_count == 2
    # Second write is the last chunk: should have fade-out on tail
    last_written = mock_stream.write.call_args_list[1][0][0]
    last_arr = np.frombuffer(last_written.tobytes(), dtype=np.int16)
    n_fade = _n_fade(sample_rate)
    assert last_arr[-1] == 0
    assert last_arr[-n_fade] == 500


@pytest.mark.asyncio
async def test_play_stream_does_not_write_pending_on_interrupt():
    """When interrupted after stream ends, pending last chunk is not written."""
    pcm_bytes = np.zeros(480, dtype=np.int16).tobytes()
    chunk = AudioChunk(data=pcm_bytes, sample_rate=24000, channels=1)
    call_count = [0]

    async def chunk_iter():
        yield chunk
        yield chunk
        yield chunk

    def is_interrupted():
        call_count[0] += 1
        return call_count[0] > 3

    mock_stream = MagicMock()
    with patch("src.voice_assistant.audio.output.playback.sd.OutputStream", return_value=mock_stream):
        await play_stream(chunk_iter(), is_interrupted=is_interrupted)

    # Two writes (chunk1 when chunk2 arrived, chunk2 when chunk3 arrived); pending chunk3 not written
    assert mock_stream.write.call_count == 2
