"""Tests for UtteranceSegmenter."""

import queue
import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch

from tank_backend.audio.input.segmenter import UtteranceSegmenter, Utterance
from tank_backend.audio.input.types import SegmenterConfig
from tank_backend.audio.input.mic import AudioFrame
from tank_backend.audio.input.vad import VADStatus, VADResult
from tank_backend.core.shutdown import GracefulShutdown


def generate_speech_frame(sample_rate=16000, frame_ms=20):
    """Generate a speech-like audio frame."""
    n_samples = int(sample_rate * frame_ms / 1000)
    t = np.linspace(0, frame_ms / 1000, n_samples)
    signal = 0.3 * np.sin(2 * np.pi * 500 * t)
    return signal.astype(np.float32)


def generate_silence_frame(sample_rate=16000, frame_ms=20):
    """Generate a silence audio frame."""
    n_samples = int(sample_rate * frame_ms / 1000)
    return np.zeros(n_samples, dtype=np.float32)


class TestSegmenterIntegration:
    """Test UtteranceSegmenter integration with VAD."""

    @pytest.fixture
    def stop_signal(self):
        """Create stop signal."""
        return GracefulShutdown()

    @pytest.fixture
    def frames_queue(self):
        """Create frames queue."""
        return queue.Queue()

    @pytest.fixture
    def utterance_queue(self):
        """Create utterance queue."""
        return queue.Queue(maxsize=20)

    @pytest.fixture
    def segmenter(self, stop_signal, frames_queue, utterance_queue):
        """Create segmenter instance."""
        cfg = SegmenterConfig()
        return UtteranceSegmenter(
            stop_signal=stop_signal,
            cfg=cfg,
            frames_queue=frames_queue,
            utterance_queue=utterance_queue,
        )

    def test_segmenter_forwards_frames_to_vad(self, segmenter, frames_queue):
        """Test that segmenter forwards frames to VAD."""
        frame_pcm = generate_speech_frame()
        frame = AudioFrame(
            pcm=frame_pcm,
            sample_rate=16000,
            timestamp_s=1000.0,
        )
        
        frames_queue.put(frame)
        
        # Mock VAD to return controllable result
        with patch.object(segmenter._vad, 'process_frame') as mock_vad:
            mock_vad.return_value = VADResult(status=VADStatus.NO_SPEECH)
            
            segmenter.handle(frame)
            
            # Verify VAD was called with correct frame
            mock_vad.assert_called_once()
            call_args = mock_vad.call_args
            assert np.array_equal(call_args[1]['pcm'], frame_pcm)
            assert call_args[1]['timestamp_s'] == 1000.0

    def test_end_speech_creates_utterance_in_queue(self, segmenter, frames_queue, utterance_queue):
        """Test that END_SPEECH creates Utterance in queue."""
        frame_pcm = generate_speech_frame()
        frame = AudioFrame(
            pcm=frame_pcm,
            sample_rate=16000,
            timestamp_s=1000.0,
        )
        
        # Mock VAD to return END_SPEECH with utterance
        utterance_pcm = np.concatenate([frame_pcm, frame_pcm])
        with patch.object(segmenter._vad, 'process_frame') as mock_vad:
            mock_vad.return_value = VADResult(
                status=VADStatus.END_SPEECH,
                utterance_pcm=utterance_pcm,
                sample_rate=16000,
                started_at_s=999.0,
                ended_at_s=1000.0,
            )
            
            segmenter.handle(frame)
            
            # Verify utterance was created and put in queue
            assert not utterance_queue.empty()
            utterance = utterance_queue.get()
            assert isinstance(utterance, Utterance)
            assert np.array_equal(utterance.pcm, utterance_pcm)
            assert utterance.sample_rate == 16000
            assert utterance.started_at_s == 999.0
            assert utterance.ended_at_s == 1000.0

    def test_no_speech_does_not_create_utterance(self, segmenter, frames_queue, utterance_queue):
        """Test that NO_SPEECH does not create Utterance."""
        frame_pcm = generate_silence_frame()
        frame = AudioFrame(
            pcm=frame_pcm,
            sample_rate=16000,
            timestamp_s=1000.0,
        )
        
        # Mock VAD to return NO_SPEECH
        with patch.object(segmenter._vad, 'process_frame') as mock_vad:
            mock_vad.return_value = VADResult(status=VADStatus.NO_SPEECH)
            
            segmenter.handle(frame)
            
            # Verify no utterance was created
            assert utterance_queue.empty()

    def test_in_speech_does_not_create_utterance(self, segmenter, frames_queue, utterance_queue):
        """Test that IN_SPEECH does not create Utterance."""
        frame_pcm = generate_speech_frame()
        frame = AudioFrame(
            pcm=frame_pcm,
            sample_rate=16000,
            timestamp_s=1000.0,
        )
        
        # Mock VAD to return IN_SPEECH
        with patch.object(segmenter._vad, 'process_frame') as mock_vad:
            mock_vad.return_value = VADResult(status=VADStatus.IN_SPEECH)
            
            segmenter.handle(frame)
            
            # Verify no utterance was created
            assert utterance_queue.empty()

    def test_vad_in_speech_triggers_interrupt_once_per_utterance(self, stop_signal, frames_queue, utterance_queue):
        """When VAD enters IN_SPEECH, interrupt callback fires once per utterance."""
        cfg = SegmenterConfig()
        on_interrupt = Mock()
        segmenter = UtteranceSegmenter(
            stop_signal=stop_signal,
            cfg=cfg,
            frames_queue=frames_queue,
            utterance_queue=utterance_queue,
            on_speech_interrupt=on_interrupt,
        )

        frame = AudioFrame(
            pcm=generate_speech_frame(),
            sample_rate=16000,
            timestamp_s=1000.0,
        )

        with patch.object(segmenter._vad, "process_frame") as mock_vad:
            mock_vad.return_value = VADResult(status=VADStatus.IN_SPEECH)
            segmenter.handle(frame)
            segmenter.handle(frame)
            segmenter.handle(frame)

        assert on_interrupt.call_count == 1

    def test_vad_interrupt_resets_after_end_speech(self, stop_signal, frames_queue, utterance_queue):
        """After END_SPEECH (or NO_SPEECH), next utterance should trigger interrupt again."""
        cfg = SegmenterConfig()
        on_interrupt = Mock()
        segmenter = UtteranceSegmenter(
            stop_signal=stop_signal,
            cfg=cfg,
            frames_queue=frames_queue,
            utterance_queue=utterance_queue,
            on_speech_interrupt=on_interrupt,
        )

        frame = AudioFrame(
            pcm=generate_speech_frame(),
            sample_rate=16000,
            timestamp_s=1000.0,
        )

        with patch.object(segmenter._vad, "process_frame") as mock_vad:
            mock_vad.side_effect = [
                VADResult(status=VADStatus.IN_SPEECH),
                VADResult(status=VADStatus.IN_SPEECH),
                VADResult(status=VADStatus.END_SPEECH, utterance_pcm=np.array([1], dtype=np.float32)),
                VADResult(status=VADStatus.NO_SPEECH),
                VADResult(status=VADStatus.IN_SPEECH),
            ]
            segmenter.handle(frame)  # IN_SPEECH -> trigger
            segmenter.handle(frame)  # IN_SPEECH -> no trigger
            segmenter.handle(frame)  # END_SPEECH -> reset
            segmenter.handle(frame)  # NO_SPEECH -> ensure reset
            segmenter.handle(frame)  # IN_SPEECH -> trigger again

        assert on_interrupt.call_count == 2

    def test_drop_oldest_when_queue_full(self, segmenter, frames_queue, utterance_queue):
        """Test that drop_oldest strategy is used when queue is full."""
        # Fill queue to capacity
        for i in range(20):
            utterance = Utterance(
                pcm=np.array([i], dtype=np.float32),
                sample_rate=16000,
                started_at_s=1000.0 + i,
                ended_at_s=1000.1 + i,
            )
            utterance_queue.put(utterance)
        
        assert utterance_queue.full()
        
        frame_pcm = generate_speech_frame()
        frame = AudioFrame(
            pcm=frame_pcm,
            sample_rate=16000,
            timestamp_s=2000.0,
        )
        
        # Mock VAD to return END_SPEECH
        utterance_pcm = frame_pcm
        with patch.object(segmenter._vad, 'process_frame') as mock_vad:
            mock_vad.return_value = VADResult(
                status=VADStatus.END_SPEECH,
                utterance_pcm=utterance_pcm,
                sample_rate=16000,
                started_at_s=1999.0,
                ended_at_s=2000.0,
            )
            
            segmenter.handle(frame)
            
            # Verify queue is still full
            assert utterance_queue.full()
            
            # Verify oldest utterance (with pcm=[0]) was removed
            # and new utterance was added
            utterances = []
            while not utterance_queue.empty():
                utterances.append(utterance_queue.get())
            
            # Should have 20 utterances
            assert len(utterances) == 20
            
            # First utterance should NOT be the one with pcm=[0]
            assert not np.array_equal(utterances[0].pcm, np.array([0], dtype=np.float32))
            
            # Last utterance should be the new one
            assert np.array_equal(utterances[-1].pcm, utterance_pcm)

    def test_flush_on_shutdown(self, segmenter, utterance_queue):
        """Test that flush is called on shutdown."""
        # Mock VAD flush
        with patch.object(segmenter._vad, 'flush') as mock_flush:
            mock_flush.return_value = VADResult(
                status=VADStatus.END_SPEECH,
                utterance_pcm=np.array([1, 2, 3], dtype=np.float32),
                sample_rate=16000,
                started_at_s=1000.0,
                ended_at_s=1001.0,
            )
            
            # Simulate shutdown
            segmenter._stop_signal.stop()
            
            # Call cleanup (normally called by QueueWorker on shutdown)
            segmenter.cleanup()
            
            # Verify flush was called
            mock_flush.assert_called_once()
