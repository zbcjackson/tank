"""Tests for ClientAudioCapture."""

import asyncio
import queue
import pytest
import numpy as np
from unittest.mock import MagicMock, patch, AsyncMock

from tank_cli.cli.audio_capture import ClientAudioCapture
from tank_cli.audio.input.types import AudioFrame
from tank_cli.core.shutdown import GracefulShutdown

MODULE = "tank_cli.cli.audio_capture"


@pytest.fixture
def shutdown():
    return GracefulShutdown()


@pytest.mark.asyncio
async def test_drain_to_ws_converts_float32_to_int16(shutdown):
    """Verify float32 PCM frames are converted to int16 bytes before sending."""
    with patch(f"{MODULE}.Mic") as MockMic:
        MockMic.return_value = MagicMock()
        capture = ClientAudioCapture(shutdown=shutdown)

        # Push a known float32 frame into the internal queue
        pcm = np.array([0.5, -0.5, 0.0, 1.0], dtype=np.float32)
        frame = AudioFrame(pcm=pcm, sample_rate=16000, timestamp_s=1000.0)
        capture._frames_queue.put(frame)

        sent_data = []

        async def mock_send(data: bytes):
            sent_data.append(data)
            # Stop after first send
            shutdown.stop()

        await capture.drain_to_ws(mock_send)

        assert len(sent_data) == 1
        result = np.frombuffer(sent_data[0], dtype=np.int16)
        expected = (pcm * 32768.0).astype(np.int16)
        np.testing.assert_array_equal(result, expected)


@pytest.mark.asyncio
async def test_drain_to_ws_sleeps_on_empty_queue(shutdown):
    """When queue is empty, drain_to_ws should sleep and not crash."""
    with patch(f"{MODULE}.Mic") as MockMic:
        MockMic.return_value = MagicMock()
        capture = ClientAudioCapture(shutdown=shutdown)

        call_count = [0]

        async def mock_send(data: bytes):
            call_count[0] += 1

        # Stop after a short delay
        async def stop_soon():
            await asyncio.sleep(0.05)
            shutdown.stop()

        await asyncio.gather(
            capture.drain_to_ws(mock_send),
            stop_soon(),
        )

        # Nothing was sent since queue was empty
        assert call_count[0] == 0


@pytest.mark.asyncio
async def test_drain_to_ws_sends_multiple_frames(shutdown):
    """Multiple frames in queue should all be sent."""
    with patch(f"{MODULE}.Mic") as MockMic:
        MockMic.return_value = MagicMock()
        capture = ClientAudioCapture(shutdown=shutdown)

        for i in range(3):
            pcm = np.array([0.1 * i], dtype=np.float32)
            capture._frames_queue.put(
                AudioFrame(pcm=pcm, sample_rate=16000, timestamp_s=1000.0 + i)
            )

        sent_data = []
        send_count = [0]

        async def mock_send(data: bytes):
            sent_data.append(data)
            send_count[0] += 1
            if send_count[0] >= 3:
                shutdown.stop()

        await capture.drain_to_ws(mock_send)
        assert len(sent_data) == 3


def test_start_calls_mic_start(shutdown):
    """start() should delegate to Mic.start()."""
    with patch(f"{MODULE}.Mic") as MockMic:
        mock_mic = MagicMock()
        MockMic.return_value = mock_mic
        capture = ClientAudioCapture(shutdown=shutdown)
        capture.start()
        mock_mic.start.assert_called_once()


def test_stop_calls_mic_join(shutdown):
    """stop() should call Mic.join()."""
    with patch(f"{MODULE}.Mic") as MockMic:
        mock_mic = MagicMock()
        MockMic.return_value = mock_mic
        capture = ClientAudioCapture(shutdown=shutdown)
        capture.stop()
        mock_mic.join.assert_called_once_with(timeout=2)
