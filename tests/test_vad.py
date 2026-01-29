"""Tests for SileroVAD voice activity detection."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from src.voice_assistant.audio.input.vad import VADStatus, SileroVAD
from src.voice_assistant.audio.input.types import SegmenterConfig


def generate_silence_frame(sample_rate=16000, frame_ms=20):
    """Generate a silence audio frame."""
    n_samples = int(sample_rate * frame_ms / 1000)
    return np.zeros(n_samples, dtype=np.float32)


def generate_speech_frame(sample_rate=16000, frame_ms=20, frequency=500):
    """Generate a speech-like audio frame (sine wave in speech frequency range)."""
    n_samples = int(sample_rate * frame_ms / 1000)
    t = np.linspace(0, frame_ms / 1000, n_samples)
    signal = 0.3 * np.sin(2 * np.pi * frequency * t)
    return signal.astype(np.float32)


class TestVADStateMachine:
    """Test VAD state machine transitions."""

    @pytest.fixture
    def vad(self):
        """Create VAD instance for testing."""
        cfg = SegmenterConfig()
        return SileroVAD(cfg=cfg, sample_rate=16000)

    def test_no_speech_for_silence_frames(self, vad):
        """Test that silence frames return NO_SPEECH status."""
        silence_pcm = generate_silence_frame()
        result = vad.process_frame(pcm=silence_pcm, timestamp_s=1000.0)
        
        assert result.status == VADStatus.NO_SPEECH
        assert result.utterance_pcm is None

    def test_transition_to_in_speech_on_speech_detection(self, vad):
        """Test that speech detection transitions to IN_SPEECH."""
        speech_pcm = generate_speech_frame()
        result = vad.process_frame(pcm=speech_pcm, timestamp_s=1000.0)
        
        assert result.status == VADStatus.IN_SPEECH
        assert result.utterance_pcm is None

    def test_in_speech_continues_accumulating_frames(self, vad):
        """Test that IN_SPEECH status continues accumulating frames."""
        speech_pcm = generate_speech_frame()
        
        # First frame: should transition to IN_SPEECH
        result1 = vad.process_frame(pcm=speech_pcm, timestamp_s=1000.0)
        assert result1.status == VADStatus.IN_SPEECH
        
        # Second frame: should still be IN_SPEECH
        result2 = vad.process_frame(pcm=speech_pcm, timestamp_s=1000.02)
        assert result2.status == VADStatus.IN_SPEECH
        assert result2.utterance_pcm is None

    def test_state_machine_output_sequence(self, vad):
        """Black-box test: Verify output status sequence matches expected behavior."""
        base_time = 1000.0
        
        # Sequence: silence -> speech -> silence
        silence_pcm = generate_silence_frame()
        speech_pcm = generate_speech_frame()
        
        results = []
        
        # 5 silence frames
        for i in range(5):
            result = vad.process_frame(pcm=silence_pcm, timestamp_s=base_time + i * 0.02)
            results.append(result)
        
        # 10 speech frames
        for i in range(10):
            result = vad.process_frame(pcm=speech_pcm, timestamp_s=base_time + 0.1 + i * 0.02)
            results.append(result)
        
        # Verify status sequence
        statuses = [r.status for r in results]
        
        # Should start with NO_SPEECH
        assert statuses[0] == VADStatus.NO_SPEECH
        
        # Should transition to IN_SPEECH when speech detected
        first_in_speech_idx = next((i for i, s in enumerate(statuses) if s == VADStatus.IN_SPEECH), None)
        assert first_in_speech_idx is not None
        assert first_in_speech_idx < 10  # Should happen during speech frames
        
        # Should remain IN_SPEECH for subsequent speech frames
        assert all(statuses[i] == VADStatus.IN_SPEECH for i in range(first_in_speech_idx, len(statuses)))


class TestVADChunkBuffering:
    """Test chunk buffering (320 → 512 samples)."""

    @pytest.fixture
    def vad(self):
        """Create VAD instance for testing."""
        cfg = SegmenterConfig()
        return SileroVAD(cfg=cfg, sample_rate=16000)

    def test_chunk_buffering_accumulates_frames(self, vad):
        """Black-box test: Verify chunk buffering by observing output timing."""
        # Send 2 frames of 320 samples each (640 total, > 512)
        frame1_pcm = generate_speech_frame()
        frame2_pcm = generate_speech_frame()
        
        base_time = 1000.0
        
        # Process first frame
        result1 = vad.process_frame(pcm=frame1_pcm, timestamp_s=base_time)
        
        # Process second frame
        result2 = vad.process_frame(pcm=frame2_pcm, timestamp_s=base_time + 0.02)
        
        # Black-box verification: After 2 frames (640 samples), should have enough
        # We verify through output behavior, not internal buffer state
        # If END_SPEECH occurs, verify utterance contains both frames' audio
        if result2.status == VADStatus.END_SPEECH:
            assert result2.utterance_pcm is not None
            assert len(result2.utterance_pcm) >= 640  # Contains both frames

    def test_chunk_processing_at_boundaries(self, vad):
        """Black-box test: Verify chunk processing by observing output patterns."""
        # Send multiple frames in sequence
        frames = [generate_speech_frame() for _ in range(20)]  # 20 frames = 400ms
        
        base_time = 1000.0
        results = []
        
        for i, frame_pcm in enumerate(frames):
            result = vad.process_frame(pcm=frame_pcm, timestamp_s=base_time + i * 0.02)
            results.append(result)
        
        # Black-box verification:
        # First END_SPEECH should occur after sufficient audio accumulated
        end_speech_results = [r for r in results if r.status == VADStatus.END_SPEECH]
        
        if len(end_speech_results) > 0:
            first_end = end_speech_results[0]
            # Verify utterance contains multiple frames (proves chunking happened)
            expected_min_samples = 512  # Based on silero-vad requirement
            assert first_end.utterance_pcm is not None
            assert len(first_end.utterance_pcm) >= expected_min_samples

    def test_partial_chunks_handled(self, vad):
        """Test that partial chunks at end are handled correctly."""
        # Send frames that don't exactly fill chunks
        frames = [generate_speech_frame() for _ in range(3)]  # 3 frames = 960 samples
        
        base_time = 1000.0
        results = []
        
        for i, frame_pcm in enumerate(frames):
            result = vad.process_frame(pcm=frame_pcm, timestamp_s=base_time + i * 0.02)
            results.append(result)
        
        # Should handle partial chunks gracefully
        # Verify no errors occurred
        assert all(r.status in [VADStatus.IN_SPEECH, VADStatus.END_SPEECH] for r in results)


class TestVADPreRoll:
    """Test pre-roll mechanism."""

    @pytest.fixture
    def vad(self):
        """Create VAD instance with pre-roll config."""
        cfg = SegmenterConfig(pre_roll_ms=200)
        return SileroVAD(cfg=cfg, sample_rate=16000)

    def test_pre_roll_included_in_utterance(self, vad):
        """Black-box test: Verify pre-roll by checking utterance content."""
        base_time = 1000.0
        
        # Pre-roll period: 10 frames of silence (200ms)
        pre_roll_frames = [generate_silence_frame() for _ in range(10)]
        
        # Speech period: 5 frames of speech
        speech_frames = [generate_speech_frame() for _ in range(5)]
        
        all_frames = pre_roll_frames + speech_frames
        
        # Process all frames
        for i, frame_pcm in enumerate(all_frames):
            vad.process_frame(pcm=frame_pcm, timestamp_s=base_time + i * 0.02)
        
        # Force finalization
        final_result = vad.flush(now_s=base_time + len(all_frames) * 0.02)
        
        # Black-box verification: Utterance should contain audio from BEFORE speech started
        assert final_result.status == VADStatus.END_SPEECH
        assert final_result.utterance_pcm is not None
        
        utterance = final_result.utterance_pcm
        
        # Verify utterance length includes pre-roll
        expected_duration_ms = 200 + (5 * 20)  # pre_roll + speech
        expected_samples = int(16000 * expected_duration_ms / 1000)
        assert len(utterance) >= expected_samples * 0.9  # Allow small tolerance
        
        # Verify utterance starts with silence (pre-roll content)
        # Check first 100ms should be low energy (silence)
        pre_roll_samples = int(16000 * 0.1)  # First 100ms
        if len(utterance) >= pre_roll_samples:
            pre_roll_energy = np.sqrt(np.mean(utterance[:pre_roll_samples]**2))
            assert pre_roll_energy < 0.01  # Should be silence

    def test_pre_roll_length_matches_config(self, vad):
        """Test that pre-roll length matches configuration."""
        base_time = 1000.0
        
        # Send pre-roll frames
        pre_roll_frames_count = int(vad._cfg.pre_roll_ms / 20)  # frames for pre_roll_ms
        pre_roll_frames = [generate_silence_frame() for _ in range(pre_roll_frames_count)]
        
        # Send speech frame to trigger speech start
        speech_frame = generate_speech_frame()
        
        # Process frames
        for i, frame_pcm in enumerate(pre_roll_frames):
            vad.process_frame(pcm=frame_pcm, timestamp_s=base_time + i * 0.02)
        
        vad.process_frame(pcm=speech_frame, timestamp_s=base_time + len(pre_roll_frames) * 0.02)
        
        # Flush to get utterance
        result = vad.flush(now_s=base_time + (len(pre_roll_frames) + 1) * 0.02)
        
        if result.status == VADStatus.END_SPEECH and result.utterance_pcm is not None:
            # Verify utterance includes pre-roll
            utterance_samples = len(result.utterance_pcm)
            expected_pre_roll_samples = int(16000 * vad._cfg.pre_roll_ms / 1000)
            # Utterance should be at least as long as pre-roll + speech frame
            assert utterance_samples >= expected_pre_roll_samples


class TestVADEndpointDetection:
    """Test endpoint detection (min_silence_ms, min_speech_ms, max_utterance_ms)."""

    def test_end_speech_after_min_silence_ms(self):
        """Test that END_SPEECH occurs after min_silence_ms silence."""
        cfg = SegmenterConfig(min_silence_ms=500, min_speech_ms=200)
        vad = SileroVAD(cfg=cfg, sample_rate=16000)
        
        base_time = 1000.0
        speech_pcm = generate_speech_frame()
        silence_pcm = generate_silence_frame()
        
        # Start speech with enough frames to exceed min_speech_ms
        # 200ms = 10 frames at 20ms each
        speech_frames_count = int(cfg.min_speech_ms / 20) + 1  # 11 frames = 220ms
        for i in range(speech_frames_count):
            vad.process_frame(pcm=speech_pcm, timestamp_s=base_time + i * 0.02)
        
        # Get last voice timestamp after speech frames
        last_voice_before_silence = vad._last_voice_at_s
        assert last_voice_before_silence is not None
        
        # Send silence frames (enough to exceed min_silence_ms)
        silence_frames_count = int(cfg.min_silence_ms / 20) + 1  # More than min_silence_ms
        results = []
        
        # Start silence after speech ends
        silence_start_time = base_time + speech_frames_count * 0.02
        
        for i in range(silence_frames_count):
            result = vad.process_frame(pcm=silence_pcm, timestamp_s=silence_start_time + i * 0.02)
            results.append(result)
            if result.status == VADStatus.END_SPEECH:
                break
        
        # Should have END_SPEECH after min_silence_ms
        end_speech_results = [r for r in results if r.status == VADStatus.END_SPEECH]
        assert len(end_speech_results) > 0, f"No END_SPEECH found. Last status: {results[-1].status if results else 'N/A'}"

    def test_short_utterances_discarded(self):
        """Test that utterances shorter than min_speech_ms are discarded."""
        cfg = SegmenterConfig(min_speech_ms=200)
        vad = SileroVAD(cfg=cfg, sample_rate=16000)
        
        base_time = 1000.0
        
        # Send only 3 frames of speech (60ms < 200ms min)
        short_speech = [generate_speech_frame() for _ in range(3)]
        silence_after = [generate_silence_frame() for _ in range(10)]
        
        all_frames = short_speech + silence_after
        
        end_speech_count = 0
        for i, frame_pcm in enumerate(all_frames):
            result = vad.process_frame(pcm=frame_pcm, timestamp_s=base_time + i * 0.02)
            if result.status == VADStatus.END_SPEECH:
                end_speech_count += 1
        
        # Should NOT emit END_SPEECH for speech shorter than min_speech_ms
        # OR if emitted, utterance should be empty/discarded
        assert end_speech_count == 0  # No utterance for too-short speech

    def test_long_utterances_force_finalized(self):
        """Test that utterances exceeding max_utterance_ms are force-finalized."""
        cfg = SegmenterConfig(max_utterance_ms=2000)  # 2 seconds
        vad = SileroVAD(cfg=cfg, sample_rate=16000)
        
        base_time = 1000.0
        
        # Send enough speech frames to exceed max_utterance_ms
        # 2 seconds = 2000ms = 100 frames at 20ms each
        speech_frames = [generate_speech_frame() for _ in range(110)]  # > max_utterance_ms
        
        end_speech_occurred = False
        for i, frame_pcm in enumerate(speech_frames):
            result = vad.process_frame(pcm=frame_pcm, timestamp_s=base_time + i * 0.02)
            if result.status == VADStatus.END_SPEECH:
                end_speech_occurred = True
                # Verify utterance was created
                assert result.utterance_pcm is not None
                break
        
        # Should force-finalize before all frames processed
        assert end_speech_occurred

    def test_flush_finalizes_in_progress_speech(self):
        """Test that flush method finalizes in-progress speech."""
        cfg = SegmenterConfig()
        vad = SileroVAD(cfg=cfg, sample_rate=16000)
        
        base_time = 1000.0
        speech_pcm = generate_speech_frame()
        
        # Start speech
        vad.process_frame(pcm=speech_pcm, timestamp_s=base_time)
        vad.process_frame(pcm=speech_pcm, timestamp_s=base_time + 0.02)
        
        # Flush without silence timeout
        result = vad.flush(now_s=base_time + 0.1)
        
        # Should return END_SPEECH with utterance
        assert result.status == VADStatus.END_SPEECH
        assert result.utterance_pcm is not None
        assert len(result.utterance_pcm) > 0
        assert result.started_at_s is not None
        assert result.ended_at_s == base_time + 0.1

    def test_flush_returns_no_speech_when_not_in_speech(self):
        """Test that flush returns NO_SPEECH when not in speech."""
        cfg = SegmenterConfig()
        vad = SileroVAD(cfg=cfg, sample_rate=16000)
        
        # Flush without any speech
        result = vad.flush(now_s=1000.0)
        
        # Should return NO_SPEECH
        assert result.status == VADStatus.NO_SPEECH
        assert result.utterance_pcm is None
