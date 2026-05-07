"""Tests for ClientAudioPlayback."""

from unittest.mock import patch

import pytest

from tank_cli.audio.frame import encode_audio_frame
from tank_cli.audio.output.types import AudioChunk
from tank_cli.cli.audio_playback import ClientAudioPlayback
from tank_cli.core.shutdown import GracefulShutdown

MODULE = "tank_cli.cli.audio_playback"


@pytest.fixture
def shutdown():
    return GracefulShutdown()


@pytest.fixture
def playback(shutdown):
    with patch(f"{MODULE}.PlaybackWorker"):
        return ClientAudioPlayback(shutdown=shutdown)


def test_on_audio_chunk_decodes_frame(playback):
    """on_audio_chunk should strip the header and use the announced rate."""
    pcm = b"\x00\x01\x02\x03"
    frame = encode_audio_frame(pcm, sample_rate=22050, channels=1)

    playback.on_audio_chunk(frame)

    chunk = playback._chunk_queue.get_nowait()
    assert isinstance(chunk, AudioChunk)
    assert chunk.data == pcm
    assert chunk.sample_rate == 22050
    assert chunk.channels == 1


def test_on_audio_chunk_drops_malformed_frame(playback):
    """A frame without the magic header should be dropped, not raised."""
    playback.on_audio_chunk(b"\xde\xad\xbe\xef\x00\x00\x00\x00\x01\x02")
    assert playback._chunk_queue.empty()


def test_on_audio_chunk_drops_when_full(shutdown):
    """When queue is full, on_audio_chunk should drop without raising."""
    with patch(f"{MODULE}.PlaybackWorker"):
        playback = ClientAudioPlayback(shutdown=shutdown)
        frame = encode_audio_frame(b"\x00", sample_rate=24000, channels=1)
        for _ in range(50):
            playback.on_audio_chunk(frame)

        # This should not raise
        playback.on_audio_chunk(frame)

        # Queue size should still be 50 (maxsize)
        assert playback._chunk_queue.qsize() == 50


def test_end_stream_pushes_none(playback):
    """end_stream should push None marker into the queue."""
    playback.end_stream()

    item = playback._chunk_queue.get_nowait()
    assert item is None


def test_interrupt_sets_event_and_clears_queue(playback):
    """interrupt should set the event and clear pending chunks."""
    frame = encode_audio_frame(b"\x00\x01", sample_rate=24000, channels=1)
    playback.on_audio_chunk(frame)
    playback.on_audio_chunk(frame)
    assert playback._chunk_queue.qsize() == 2

    playback.interrupt()

    assert playback._interrupt_event.is_set()
    assert playback._chunk_queue.qsize() == 0


def test_start_delegates_to_playback_worker(playback):
    """start() should call PlaybackWorker.start()."""
    playback.start()
    playback._playback.start.assert_called_once()


def test_stop_delegates_to_playback_worker(playback):
    """stop() should call PlaybackWorker.join()."""
    playback.stop()
    playback._playback.join.assert_called_once_with(timeout=2)
