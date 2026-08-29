"""Tests for SileroVAD voice activity detection."""

import numpy as np
import pytest

from tank_backend.audio.input.smart_turn import SmartTurnAnalyzer, SmartTurnResult
from tank_backend.audio.input.types import AudioFrame, SegmenterConfig
from tank_backend.audio.input.vad import SileroVAD, VADEngine, VADStatus


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
        """Test that speech detection transitions to START_SPEECH then IN_SPEECH."""
        speech_pcm = generate_speech_frame()
        result = vad.process_frame(pcm=speech_pcm, timestamp_s=1000.0)

        # First speech frame returns START_SPEECH
        assert result.status == VADStatus.START_SPEECH
        assert result.started_at_s == 1000.0
        assert result.utterance_pcm is None

    def test_in_speech_continues_accumulating_frames(self, vad):
        """Test that IN_SPEECH status continues accumulating frames."""
        speech_pcm = generate_speech_frame()

        # First frame: should transition to START_SPEECH
        result1 = vad.process_frame(pcm=speech_pcm, timestamp_s=1000.0)
        assert result1.status == VADStatus.START_SPEECH

        # Second frame: should be IN_SPEECH
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

        # Should have START_SPEECH followed by IN_SPEECH when speech detected
        first_start_speech_idx = next(
            (i for i, s in enumerate(statuses) if s == VADStatus.START_SPEECH), None
        )
        assert first_start_speech_idx is not None
        assert first_start_speech_idx >= 5  # Should happen during speech frames

        # After START_SPEECH, should be IN_SPEECH for subsequent frames
        speech_statuses = statuses[first_start_speech_idx + 1:]
        assert all(s == VADStatus.IN_SPEECH for s in speech_statuses)


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
        vad.process_frame(pcm=frame1_pcm, timestamp_s=base_time)

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
        # First frame should be START_SPEECH, rest IN_SPEECH or END_SPEECH
        valid_statuses = [VADStatus.START_SPEECH, VADStatus.IN_SPEECH, VADStatus.END_SPEECH]
        assert all(r.status in valid_statuses for r in results)


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
            pre_roll_energy = np.sqrt(np.mean(utterance[:pre_roll_samples] ** 2))
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


class TestVADForwardsAudioFrame:
    """Test that VADProcessor forwards AudioFrame during speech for streaming ASR."""

    @pytest.fixture
    def mock_vad_processor(self):
        """Create VADProcessor with a mocked SileroVAD for deterministic control."""
        from unittest.mock import MagicMock

        from tank_backend.pipeline.bus import Bus
        from tank_backend.pipeline.processors.vad import VADProcessor

        mock_vad = MagicMock()
        bus = Bus()
        proc = VADProcessor(vad_stream=mock_vad, bus=bus)
        return proc, bus, mock_vad

    @staticmethod
    def _make_vad_result(status, utterance_pcm=None, started_at_s=None, ended_at_s=None):
        """Build a mock VADResult."""
        from unittest.mock import MagicMock
        result = MagicMock()
        result.status = status
        result.utterance_pcm = utterance_pcm
        result.started_at_s = started_at_s
        result.ended_at_s = ended_at_s
        return result

    @staticmethod
    async def _collect(proc, frame):
        """Collect all (status, output) pairs from processor.process(frame)."""
        results = []
        async for status, output in proc.process(frame):
            results.append((status, output))
        return results

    @staticmethod
    def _frame(timestamp_s):
        """Build a dummy AudioFrame for testing."""
        pcm = np.zeros(320, dtype=np.float32)
        return AudioFrame(pcm=pcm, sample_rate=16000, timestamp_s=timestamp_s)

    async def test_in_speech_yields_audio_frame(self, mock_vad_processor):
        """IN_SPEECH should forward the original AudioFrame downstream."""
        proc, bus, mock_vad = mock_vad_processor
        mock_vad.process_frame.return_value = self._make_vad_result(VADStatus.IN_SPEECH)

        frame = self._frame(1000.0)
        outputs = await self._collect(proc, frame)

        assert len(outputs) == 1
        assert outputs[0][1] is frame

    async def test_no_speech_start_from_vad(self, mock_vad_processor):
        """VAD no longer posts speech_start — ASR owns that responsibility."""
        proc, bus, mock_vad = mock_vad_processor
        speech_starts = []
        bus.subscribe("speech_start", lambda m: speech_starts.append(m))

        mock_vad.process_frame.return_value = self._make_vad_result(VADStatus.IN_SPEECH)

        for i in range(10):
            await self._collect(proc, self._frame(1000.0 + i * 0.02))
            bus.poll()

        assert len(speech_starts) == 0


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
        assert len(end_speech_results) > 0, (
            f"No END_SPEECH found. Last status: {results[-1].status if results else 'N/A'}"
        )

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


class _ScriptedAnalyzer(SmartTurnAnalyzer):
    """Scripted Smart Turn verdicts; records predict() audio for assertions.

    Skips the heavy ``__init__`` (no ONNX session) — VADStream only uses
    the two timing knobs and ``predict()``.
    """

    def __init__(
        self,
        verdicts: list[bool],
        candidate_ms: int = 250,
        delay_ms: int = 600,
        fail: bool = False,
    ):
        self.candidate_min_silence_ms = candidate_ms
        self.incomplete_delay_ms = delay_ms
        self._verdicts = list(verdicts)
        self._fail = fail
        self.calls: list[np.ndarray] = []

    def predict(self, audio, *, sample_rate=16000):  # noqa: ANN001 — test fake
        self.calls.append(np.asarray(audio))
        if self._fail:
            raise RuntimeError("scripted Smart Turn failure")
        complete = self._verdicts.pop(0) if self._verdicts else True
        return SmartTurnResult(
            complete=complete,
            probability=0.9 if complete else 0.1,
            inference_ms=1.0,
        )


def _feed(stream, frames, start_s, step_s=0.02):  # noqa: ANN001 — test helper
    """Feed frames; return (index, result) of the first END_SPEECH, or None."""
    for i, pcm in enumerate(frames):
        result = stream.process_frame(pcm=pcm, timestamp_s=start_s + i * step_s)
        if result.status == VADStatus.END_SPEECH:
            return i, result
    return None


class TestSmartTurnEndpointing:
    """VADStream × Smart Turn: candidate boundary, hold, resume-merge."""

    BASE_TIME = 1000.0
    SPEECH_FRAMES = 11  # 220ms > min_speech_ms
    # Silero's voice timestamps trail the acoustic offset by ~100ms, so a
    # 250ms candidate boundary commits ~370ms after the last speech frame.
    CANDIDATE_BUDGET_S = 0.90  # committed well before the 1000ms fallback
    FALLBACK_BUDGET_S = 1.60

    def _stream(self, analyzer, cfg=None):
        engine = VADEngine()
        return engine.create_stream(
            cfg=cfg or SegmenterConfig(min_silence_ms=1000),
            smart_turn=analyzer,
        )

    def _speech_then_silence(self, analyzer, silence_budget_s, cfg=None):
        """11 speech frames then silence; return (index, result) of END_SPEECH."""
        stream = self._stream(analyzer, cfg)
        speech = [generate_speech_frame() for _ in range(self.SPEECH_FRAMES)]
        silence = [generate_silence_frame() for _ in range(int(silence_budget_s / 0.02))]

        assert _feed(stream, speech, self.BASE_TIME) is None  # no endpoint in speech
        found = _feed(stream, silence, self.BASE_TIME + self.SPEECH_FRAMES * 0.02)
        return found, stream

    def test_no_analyzer_falls_back_to_min_silence_ms(self):
        """Without an analyzer, the configured silence timeout is the endpoint."""
        found, _ = self._speech_then_silence(None, self.FALLBACK_BUDGET_S)

        assert found is not None, "expected END_SPEECH at the plain silence policy"
        idx, _ = found
        silence_s = (idx + 1) * 0.02
        assert silence_s >= 0.60, "committed too early without an analyzer"

    def test_complete_verdict_commits_at_candidate_boundary(self):
        """complete → commit at the fast candidate boundary, not 1000ms."""
        analyzer = _ScriptedAnalyzer([True])
        found, _ = self._speech_then_silence(analyzer, self.CANDIDATE_BUDGET_S)

        assert found is not None, "complete verdict should commit at the candidate boundary"
        idx, result = found
        silence_s = (idx + 1) * 0.02
        assert silence_s < self.CANDIDATE_BUDGET_S
        assert result.utterance_pcm is not None and len(result.utterance_pcm) > 0
        assert len(analyzer.calls) == 1

    def test_incomplete_verdict_holds_then_commits(self):
        """incomplete → hold open for the incomplete window, then commit."""
        analyzer = _ScriptedAnalyzer([False], delay_ms=600)
        # Budget past candidate (~0.37s) + 0.6s hold + tolerance
        found, _ = self._speech_then_silence(analyzer, 1.30)

        assert found is not None, "hold expiry should commit the utterance"
        idx, _ = found
        silence_s = (idx + 1) * 0.02
        # The hold must actually delay the commit past the candidate boundary
        assert silence_s >= 0.50, "incomplete verdict committed without holding"
        assert silence_s < 1.30
        assert len(analyzer.calls) == 1

    def test_resume_during_hold_merges_into_one_utterance(self):
        """Speech resuming inside the hold continues the same utterance."""
        analyzer = _ScriptedAnalyzer([False, True])
        stream = self._stream(analyzer)

        t = self.BASE_TIME
        speech = [generate_speech_frame() for _ in range(self.SPEECH_FRAMES)]

        # Burst 1 → 500ms pause (crosses the candidate boundary → "incomplete"
        # hold) → burst 2 inside the hold window → final silence
        assert _feed(stream, speech, t) is None
        t += self.SPEECH_FRAMES * 0.02

        pause = [generate_silence_frame() for _ in range(25)]  # 500ms
        assert _feed(stream, pause, t) is None, "hold must swallow the pause"
        t += len(pause) * 0.02

        assert _feed(stream, speech, t) is None, "resumed speech must continue the turn"
        t += self.SPEECH_FRAMES * 0.02

        tail = [generate_silence_frame() for _ in range(40)]  # 800ms
        found = _feed(stream, tail, t)

        assert found is not None, "expected a single END_SPEECH after the tail"
        _, result = found
        assert result.utterance_pcm is not None
        # One merged utterance: both bursts + the pause (and pre-roll)
        assert len(result.utterance_pcm) / 16000 > 0.8
        # The analyzer re-adjudicated the longer utterance
        assert len(analyzer.calls) == 2
        assert analyzer.calls[1].shape[0] > analyzer.calls[0].shape[0]

    def test_analyzer_exception_commits_at_candidate_boundary(self):
        """Inference failure fails open: commit immediately, never hang."""
        analyzer = _ScriptedAnalyzer([], fail=True)
        found, _ = self._speech_then_silence(analyzer, self.CANDIDATE_BUDGET_S)

        assert found is not None, "analyzer failure must not block the endpoint"
        idx, _ = found
        assert (idx + 1) * 0.02 < self.CANDIDATE_BUDGET_S

    def test_flush_commits_held_utterance(self):
        """PTT / end-of-utterance flush force-finalizes a held segment."""
        analyzer = _ScriptedAnalyzer([False], delay_ms=600)
        stream = self._stream(analyzer)

        t = self.BASE_TIME
        speech = [generate_speech_frame() for _ in range(self.SPEECH_FRAMES)]
        assert _feed(stream, speech, t) is None
        t += self.SPEECH_FRAMES * 0.02

        pause = [generate_silence_frame() for _ in range(25)]  # enter the hold
        assert _feed(stream, pause, t) is None
        t += len(pause) * 0.02

        result = stream.flush(now_s=t)
        assert result.status == VADStatus.END_SPEECH
        assert result.utterance_pcm is not None and len(result.utterance_pcm) > 0
        # State fully reset — no leakage into the next turn
        assert stream.process_frame(
            pcm=generate_silence_frame(), timestamp_s=t + 0.02
        ).status == VADStatus.NO_SPEECH

    def test_max_utterance_cap_enforced_with_analyzer(self):
        """max_utterance_ms still force-finalizes while an analyzer is attached."""
        cfg = SegmenterConfig(min_silence_ms=1000, max_utterance_ms=1000)
        analyzer = _ScriptedAnalyzer([False] * 10)
        stream = self._stream(analyzer, cfg)

        speech = [generate_speech_frame() for _ in range(80)]  # 1600ms continuous
        found = _feed(stream, speech, self.BASE_TIME)

        assert found is not None, "hard utterance cap must fire during the hold era"
        _, result = found
        assert result.utterance_pcm is not None


class TestLargeFrameVoiceTracking:
    """Regression: frames larger than the 512-sample Silero chunk size.

    During sustained speech the transition-based VADIterator reports no
    result for full chunks; the sub-chunk leftover of each frame must
    still count as voice evidence, or mid-speech frames read as silent,
    ``_last_voice_at_s`` freezes, and a short silence boundary (Smart
    Turn's 250ms candidate) fires mid-speech.
    """

    def test_sustained_speech_tracked_across_big_frames(self):
        cfg = SegmenterConfig(min_silence_ms=250, min_speech_ms=200)
        analyzer = _ScriptedAnalyzer([True])
        stream = VADEngine().create_stream(cfg=cfg, smart_turn=analyzer)

        # 0.5s speech (25 x 20ms) fed as 100ms frames, then 1s silence
        speech = b"".join(
            generate_speech_frame().tobytes() for _ in range(25)
        )
        speech = np.frombuffer(speech, dtype=np.float32)
        silence = np.zeros(16000, dtype=np.float32)

        starts = ends = 0
        for i in range(0, len(speech), 1600):
            r = stream.process_frame(pcm=speech[i:i + 1600], timestamp_s=1000.0 + i / 16000)
            starts += r.status == VADStatus.START_SPEECH
        for i in range(0, len(silence), 1600):
            r = stream.process_frame(pcm=silence[i:i + 1600], timestamp_s=1000.5 + i / 16000)
            if r.status == VADStatus.END_SPEECH:
                ends += 1
                break

        assert starts == 1
        assert ends == 1, "utterance must complete once after trailing silence"
