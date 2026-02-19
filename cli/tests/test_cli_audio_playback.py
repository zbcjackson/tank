"""Tests for ClientAudioPlayback."""

import queue
import pytest
from unittest.mock import MagicMock, patch

from tank_cli.cli.audio_playback import ClientAudioPlayback
from tank_cli.audio.output.types import AudioChunk
from tank_cli.core.shutdown import GracefulShutdown

MODULE = "tank_cli.cli.audio_playback"


@pytest.fixture
def shutdown():
    return GracefulShutdown()


@pytest.fixture
def playback(shutdown):
    with patch(f"{MODULE}.PlaybackWorker"):
        return ClientAudioPlayback(shutdown=shutdown)


def test_on_audio_chunk_enqueues(playback):
    """on_audio_chunk should wrap bytes in AudioChunk and enqueue."""
    data = b"\x00\x01\x02\x03"
    playback.on_audio_chunk(data)

    chunk = playback._chunk_queue.get_nowait()
    assert isinstance(chunk, AudioChunk)
    assert chunk.data == data
    assert chunk.sample_rate == 24000
    assert chunk.channels == 1


def test_on_audio_chunk_drops_when_full(shutdown):
    """When queue is full, on_audio_chunk should drop without raising."""
    with patch(f"{MODULE}.PlaybackWorker"):
        playback = ClientAudioPlayback(shutdown=shutdown)
        # Fill the queue
        for _ in range(50):
            playback.on_audio_chunk(b"\x00")

        # This should not raise
        playback.on_audio_chunk(b"\xff")

        # Queue size should still be 50 (maxsize)
        assert playback._chunk_queue.qsize() == 50


def test_end_stream_pushes_none(playback):
    """end_stream should push None marker into the queue."""
    playback.end_stream()

    item = playback._chunk_queue.get_nowait()
    assert item is None


def test_interrupt_sets_event_and_clears_queue(playback):
    """interrupt should set the event and clear pending chunks."""
    playback.on_audio_chunk(b"\x00\x01")
    playback.on_audio_chunk(b"\x02\x03")
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
