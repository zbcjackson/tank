"""Tests for speaker embedding extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tank_backend.audio.input.embedding_sherpa import SherpaEmbeddingExtractor


@pytest.fixture
def mock_sherpa_extractor():
    """Mock sherpa-onnx extractor."""
    with patch("tank_backend.audio.input.embedding_sherpa._SherpaExtractor") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.dim = 192
        mock_instance.create_stream.return_value = MagicMock()
        mock_instance.compute.return_value = [0.1] * 192  # Mock embedding
        mock_cls.return_value = mock_instance
        yield mock_instance


def test_sherpa_embedding_extractor_init(mock_sherpa_extractor, tmp_path):
    """Test SherpaEmbeddingExtractor initialization."""
    model_path = tmp_path / "model.onnx"
    model_path.touch()

    extractor = SherpaEmbeddingExtractor(str(model_path), num_threads=2, provider="cpu")

    assert extractor.embedding_dim == 192
    mock_sherpa_extractor.create_stream.assert_not_called()


def test_sherpa_embedding_extractor_init_missing_model():
    """Test SherpaEmbeddingExtractor initialization with missing model."""
    with pytest.raises(FileNotFoundError):
        SherpaEmbeddingExtractor("nonexistent.onnx")


def test_sherpa_embedding_extractor_extract(mock_sherpa_extractor, tmp_path):
    """Test embedding extraction."""
    model_path = tmp_path / "model.onnx"
    model_path.touch()

    extractor = SherpaEmbeddingExtractor(str(model_path))

    # Create test audio
    audio = np.random.randn(16000).astype(np.float32)  # 1 second at 16kHz
    sample_rate = 16000

    # Extract embedding
    embedding = extractor.extract(audio, sample_rate)

    # Verify
    assert isinstance(embedding, np.ndarray)
    assert embedding.dtype == np.float32
    assert embedding.shape == (192,)
    mock_sherpa_extractor.create_stream.assert_called_once()
    mock_sherpa_extractor.compute.assert_called_once()


def test_sherpa_embedding_extractor_extract_normalizes_audio(mock_sherpa_extractor, tmp_path):
    """Test that audio is normalized to [-1, 1] range."""
    model_path = tmp_path / "model.onnx"
    model_path.touch()

    extractor = SherpaEmbeddingExtractor(str(model_path))

    # Create audio with values > 1.0
    audio = np.array([2.0, -3.0, 1.5, -2.5], dtype=np.float32)
    sample_rate = 16000

    # Extract embedding (result unused — we're testing the normalization side effect)
    extractor.extract(audio, sample_rate)

    # Verify stream.accept_waveform was called
    mock_stream = mock_sherpa_extractor.create_stream.return_value
    mock_stream.accept_waveform.assert_called_once()

    # Check that audio was normalized (max abs value should be 1.0)
    call_args = mock_stream.accept_waveform.call_args
    normalized_audio = call_args.kwargs["waveform"]
    assert np.abs(normalized_audio).max() <= 1.0


def test_sherpa_embedding_extractor_extract_converts_dtype(mock_sherpa_extractor, tmp_path):
    """Test that audio dtype is converted to float32."""
    model_path = tmp_path / "model.onnx"
    model_path.touch()

    extractor = SherpaEmbeddingExtractor(str(model_path))

    # Create audio with int16 dtype
    audio = np.array([100, -200, 300], dtype=np.int16)
    sample_rate = 16000

    # Extract embedding (result unused — we're testing the dtype conversion side effect)
    extractor.extract(audio, sample_rate)

    # Verify stream.accept_waveform was called with float32
    mock_stream = mock_sherpa_extractor.create_stream.return_value
    call_args = mock_stream.accept_waveform.call_args
    converted_audio = call_args.kwargs["waveform"]
    assert converted_audio.dtype == np.float32


def test_sherpa_embedding_extractor_close(mock_sherpa_extractor, tmp_path):
    """Test resource cleanup."""
    model_path = tmp_path / "model.onnx"
    model_path.touch()

    extractor = SherpaEmbeddingExtractor(str(model_path))
    extractor.close()

    # Sherpa-ONNX handles cleanup automatically, so no assertions needed
    # Just verify no exceptions are raised
