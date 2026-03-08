"""Tests for Sherpa-ONNX ASR engine."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

MODULE = "asr_sherpa.engine"


@pytest.fixture
def mock_sherpa():
    """Mock all sherpa-onnx internals to avoid model loading."""
    with (
        patch(f"{MODULE}.OnlineRecognizer") as mock_recognizer_cls,
        patch(f"{MODULE}.OnlineRecognizerConfig"),
        patch(f"{MODULE}.OnlineModelConfig"),
        patch(f"{MODULE}.OnlineTransducerModelConfig"),
        patch(f"{MODULE}.FeatureExtractorConfig"),
        patch(f"{MODULE}.EndpointConfig"),
        patch(f"{MODULE}.EndpointRule"),
        patch(f"{MODULE}.OnlineLMConfig"),
        patch(f"{MODULE}.OnlineCtcFstDecoderConfig"),
        patch(f"{MODULE}.Path") as mock_path_cls,
    ):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.__truediv__ = MagicMock(return_value=MagicMock(__str__=lambda s: "model.onnx"))
        mock_path_cls.return_value = mock_path

        mock_recognizer = MagicMock()
        mock_stream = MagicMock()
        mock_recognizer.create_stream.return_value = mock_stream
        mock_recognizer_cls.return_value = mock_recognizer

        yield mock_recognizer, mock_stream


def test_process_pcm_returns_text_and_endpoint(mock_sherpa):
    """process_pcm returns (text, is_endpoint) from recognizer."""
    mock_recognizer, mock_stream = mock_sherpa
    mock_recognizer.is_ready.return_value = False
    mock_recognizer.is_endpoint.return_value = False
    mock_result = MagicMock()
    mock_result.text = " hello world "
    mock_recognizer.get_result.return_value = mock_result

    from asr_sherpa.engine import SherpaASREngine

    engine = SherpaASREngine(model_dir="/fake/model")
    pcm = np.zeros(320, dtype=np.float32)
    text, is_endpoint = engine.process_pcm(pcm)

    assert text == "hello world"
    assert is_endpoint is False
    mock_stream.accept_waveform.assert_called_once()


def test_process_pcm_resets_on_endpoint(mock_sherpa):
    """When is_endpoint is True, recognizer.reset is called."""
    mock_recognizer, mock_stream = mock_sherpa
    mock_recognizer.is_ready.return_value = False
    mock_recognizer.is_endpoint.return_value = True
    mock_result = MagicMock()
    mock_result.text = " done "
    mock_recognizer.get_result.return_value = mock_result

    from asr_sherpa.engine import SherpaASREngine

    engine = SherpaASREngine(model_dir="/fake/model")
    text, is_endpoint = engine.process_pcm(np.zeros(320, dtype=np.float32))

    assert text == "done"
    assert is_endpoint is True
    mock_recognizer.reset.assert_called_once_with(mock_stream)


def test_reset_delegates_to_recognizer(mock_sherpa):
    """reset() calls recognizer.reset on the stream."""
    mock_recognizer, mock_stream = mock_sherpa

    from asr_sherpa.engine import SherpaASREngine

    engine = SherpaASREngine(model_dir="/fake/model")
    engine.reset()

    mock_recognizer.reset.assert_called_once_with(mock_stream)


def test_create_engine_factory():
    """create_engine returns a SherpaASREngine with config values."""
    with patch(f"{MODULE}.SherpaASREngine.__init__", return_value=None) as mock_init:
        # Need to patch Path.exists too since __init__ is not fully mocked
        from asr_sherpa import create_engine

        create_engine({
            "model_dir": "/my/model",
            "num_threads": 2,
            "sample_rate": 8000,
        })

        mock_init.assert_called_once_with(
            model_dir="/my/model",
            num_threads=2,
            sample_rate=8000,
        )
