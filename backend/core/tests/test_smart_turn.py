"""Tests for the Smart Turn end-of-turn analyzer.

The ONNX session and Whisper feature extractor are faked (``object.__new__``
construction mirrors the upstream s2s test suite) — no model file is needed.
"""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from tank_backend.audio.input.smart_turn import (
    MAX_AUDIO_SAMPLES,
    MIN_AUDIO_SAMPLES,
    MODEL_SAMPLE_RATE,
    SmartTurnAnalyzer,
)
from tank_backend.config.models import SmartTurnConfig


def make_analyzer(
    probability: float, threshold: float = 0.5,
) -> tuple[SmartTurnAnalyzer, MagicMock, MagicMock]:
    """Build an analyzer whose session always returns ``probability``.

    Returns ``(analyzer, session_mock, feature_extractor_mock)`` so tests
    can assert on the calls without poking the typed attributes.
    """
    analyzer = object.__new__(SmartTurnAnalyzer)
    analyzer.threshold = threshold
    analyzer.candidate_min_silence_ms = 250
    analyzer.incomplete_delay_ms = 600
    analyzer._lock = threading.Lock()
    analyzer._input_name = "audio_input"

    session = MagicMock()
    session.run.return_value = [np.array([[probability]], dtype=np.float32)]
    analyzer.session = session

    feature_extractor = MagicMock()
    feature_extractor.return_value = SimpleNamespace(
        input_features=np.zeros((1, 80, 800), dtype=np.float32),
    )
    analyzer._feature_extractor = feature_extractor
    return analyzer, session, feature_extractor


class TestPrepareAudio:
    """Audio windowing: resample → tail 8 s → left-pad."""

    def test_keeps_latest_eight_seconds(self):
        audio = np.arange(200000, dtype=np.float32)
        prepared = SmartTurnAnalyzer._prepare_audio(audio, MODEL_SAMPLE_RATE)

        assert prepared.shape == (MAX_AUDIO_SAMPLES,)
        np.testing.assert_array_equal(prepared, audio[-MAX_AUDIO_SAMPLES:])

    def test_left_pads_short_audio(self):
        audio = np.full(32000, 0.5, dtype=np.float32)
        prepared = SmartTurnAnalyzer._prepare_audio(audio, MODEL_SAMPLE_RATE)

        assert prepared.shape == (MAX_AUDIO_SAMPLES,)
        # Newest audio stays at the end of the window
        np.testing.assert_array_equal(prepared[-32000:], audio)
        np.testing.assert_array_equal(prepared[:-32000], np.zeros_like(prepared[:-32000]))

    def test_exact_length_unchanged(self):
        audio = np.ones(MAX_AUDIO_SAMPLES, dtype=np.float32)
        prepared = SmartTurnAnalyzer._prepare_audio(audio, MODEL_SAMPLE_RATE)
        np.testing.assert_array_equal(prepared, audio)

    def test_resamples_non_16k(self):
        audio = np.ones(8000, dtype=np.float32)  # 0.5 s at 32 kHz
        prepared = SmartTurnAnalyzer._prepare_audio(audio, 32000)

        assert prepared.shape == (MAX_AUDIO_SAMPLES,)
        assert prepared[-4000:].max() == pytest.approx(1.0, abs=1e-3)

    def test_rejects_non_mono(self):
        stereo = np.zeros((100, 2), dtype=np.float32)
        with pytest.raises(ValueError, match="mono 1-D"):
            SmartTurnAnalyzer._prepare_audio(stereo, MODEL_SAMPLE_RATE)

    def test_rejects_nonpositive_sample_rate(self):
        with pytest.raises(ValueError, match="positive"):
            SmartTurnAnalyzer._prepare_audio(np.zeros(100, dtype=np.float32), 0)


class TestPredict:
    """Verdict interpretation and the model I/O contract."""

    def test_probability_above_threshold_is_complete(self):
        analyzer, _, _ = make_analyzer(probability=0.75)
        result = analyzer.predict(np.zeros(MODEL_SAMPLE_RATE * 2, dtype=np.float32))

        assert result.complete is True
        assert result.probability == pytest.approx(0.75)
        assert result.inference_ms >= 0

    def test_probability_at_or_below_threshold_is_incomplete(self):
        analyzer, _, _ = make_analyzer(probability=0.45)
        result = analyzer.predict(np.zeros(MODEL_SAMPLE_RATE * 2, dtype=np.float32))

        assert result.complete is False

    def test_threshold_comparison_is_strict(self):
        analyzer, _, _ = make_analyzer(probability=0.5)
        assert analyzer.predict(np.zeros(32000, dtype=np.float32)).complete is False

    def test_short_audio_short_circuits_without_inference(self):
        analyzer, session, _ = make_analyzer(probability=0.0)
        result = analyzer.predict(np.zeros(MIN_AUDIO_SAMPLES - 1, dtype=np.float32))

        assert result.complete is True
        session.run.assert_not_called()

    def test_nonfinite_probability_raises(self):
        analyzer, _, _ = make_analyzer(probability=float("nan"))
        with pytest.raises(RuntimeError, match="non-finite"):
            analyzer.predict(np.zeros(32000, dtype=np.float32))

    def test_feature_extractor_receives_model_contract(self):
        analyzer, session, feature_extractor = make_analyzer(probability=0.9)
        analyzer.predict(np.zeros(32000, dtype=np.float32))

        kwargs = feature_extractor.call_args.kwargs
        assert kwargs["sampling_rate"] == MODEL_SAMPLE_RATE
        assert kwargs["padding"] == "max_length"
        assert kwargs["max_length"] == MAX_AUDIO_SAMPLES
        assert kwargs["truncation"] is True
        assert kwargs["do_normalize"] is True

        called_features = session.run.call_args[0][1]["audio_input"]
        assert called_features.shape == (1, 80, 800)

    def test_mismatched_feature_shape_raises(self):
        analyzer, _, feature_extractor = make_analyzer(probability=0.9)
        feature_extractor.return_value = SimpleNamespace(
            input_features=np.zeros((1, 80, 799), dtype=np.float32),
        )
        with pytest.raises(RuntimeError, match="feature shape"):
            analyzer.predict(np.zeros(32000, dtype=np.float32))


class TestFromConfig:
    """Config-driven construction: never raises, None on the fallback paths."""

    def test_disabled_returns_none(self):
        assert SmartTurnAnalyzer.from_config(SmartTurnConfig(enabled=False)) is None

    def test_missing_model_returns_none(self, tmp_path):
        cfg = SmartTurnConfig(enabled=True, model_path=str(tmp_path / "absent.onnx"))
        assert SmartTurnAnalyzer.from_config(cfg) is None
