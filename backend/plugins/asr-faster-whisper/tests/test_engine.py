"""Test Faster-Whisper ASR plugin."""

from unittest.mock import MagicMock, patch

import numpy as np

MODULE = "asr_faster_whisper.engine"


def _make_engine(**overrides):
    """Create an engine with WhisperModel patched (no model download)."""
    config = {"model_size": "base", "device": "cpu", "compute_type": "int8", **overrides}
    with patch(f"{MODULE}.WhisperModel") as mock_model_cls:
        from asr_faster_whisper import create_engine

        engine = create_engine(config)
        return engine, mock_model_cls.return_value


def test_create_engine_factory():
    """Factory maps config values to the engine constructor."""
    with patch(
        f"{MODULE}.FasterWhisperASREngine.__init__", return_value=None
    ) as mock_init:
        from asr_faster_whisper import create_engine

        create_engine({
            "model_size": "large-v3",
            "device": "cuda",
            "compute_type": "float16",
            "language": "en",
            "beam_size": 3,
            "sample_rate": 8000,
        })
        mock_init.assert_called_once_with(
            model_size="large-v3",
            device="cuda",
            compute_type="float16",
            language="en",
            beam_size=3,
            sample_rate=8000,
        )


def test_supports_streaming_is_false():
    """Faster-Whisper is a batch engine, not streaming."""
    engine, _ = _make_engine()
    stream = engine.create_stream()
    assert stream.supports_streaming is False


def test_sample_rate_property():
    engine, _ = _make_engine(sample_rate=8000)
    assert engine.sample_rate == 8000


def test_batch_transcription_and_language():
    """Full lifecycle: start → process_pcm → stop returns transcript + language."""
    engine, mock_model = _make_engine()
    mock_model.transcribe.return_value = (
        [MagicMock(text="hello world")],
        MagicMock(language="en", language_probability=0.99),
    )

    stream = engine.create_stream()
    stream.start()
    stream.process_pcm(np.zeros(16000, dtype=np.float32))
    result = stream.stop()

    assert result == "hello world"
    assert stream.detected_language == "en"


def test_multiple_segments_joined():
    """Segments are concatenated into a single transcript."""
    engine, mock_model = _make_engine()
    mock_model.transcribe.return_value = (
        [MagicMock(text="hello "), MagicMock(text="world")],
        MagicMock(language="en"),
    )

    stream = engine.create_stream()
    stream.start()
    stream.process_pcm(np.zeros(8000, dtype=np.float32))
    stream.process_pcm(np.zeros(8000, dtype=np.float32))
    assert stream.stop() == "hello world"


def test_stop_without_audio_returns_empty():
    engine, mock_model = _make_engine()
    stream = engine.create_stream()
    stream.start()
    assert stream.stop() == ""
    mock_model.transcribe.assert_not_called()
