"""Tests for voiceprint recognizer."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from tank_backend.audio.input.voiceprint import Utterance, VoiceprintRecognizer


@pytest.fixture
def mock_extractor():
    """Mock embedding extractor."""
    extractor = MagicMock()
    extractor.extract.return_value = np.random.randn(192).astype(np.float32)
    return extractor


@pytest.fixture
def mock_repository():
    """Mock speaker repository."""
    repository = MagicMock()
    repository.identify.return_value = "alice"
    return repository


@pytest.fixture
def sample_utterance():
    """Create a sample utterance."""
    audio = np.random.randn(16000).astype(np.float32)
    return Utterance(pcm=audio, sample_rate=16000, started_at_s=0.0, ended_at_s=1.0)


def test_voiceprint_recognizer_disabled():
    """Test voiceprint recognizer when disabled."""
    recognizer = VoiceprintRecognizer(
        extractor=None, repository=None, default_user="Unknown"
    )

    utterance = Utterance(
        pcm=np.random.randn(16000).astype(np.float32),
        sample_rate=16000,
        started_at_s=0.0,
        ended_at_s=1.0,
    )

    user = recognizer.identify(utterance)
    assert user == "Unknown"


def test_voiceprint_recognizer_enabled(mock_extractor, mock_repository, sample_utterance):
    """Test voiceprint recognizer when enabled."""
    recognizer = VoiceprintRecognizer(
        extractor=mock_extractor,
        repository=mock_repository,
        default_user="Unknown",
        threshold=0.6,
    )

    user = recognizer.identify(sample_utterance)

    assert user == "alice"
    mock_extractor.extract.assert_called_once_with(
        sample_utterance.pcm, sample_utterance.sample_rate
    )
    mock_repository.identify.assert_called_once()


def test_voiceprint_recognizer_no_match(mock_extractor, mock_repository, sample_utterance):
    """Test voiceprint recognizer when no match is found."""
    mock_repository.identify.return_value = None

    recognizer = VoiceprintRecognizer(
        extractor=mock_extractor,
        repository=mock_repository,
        default_user="Unknown",
        threshold=0.6,
    )

    user = recognizer.identify(sample_utterance)

    assert user == "Unknown"


def test_voiceprint_recognizer_extraction_fails(mock_extractor, mock_repository, sample_utterance):
    """Test voiceprint recognizer when extraction fails."""
    mock_extractor.extract.side_effect = RuntimeError("Extraction failed")

    recognizer = VoiceprintRecognizer(
        extractor=mock_extractor,
        repository=mock_repository,
        default_user="Unknown",
        threshold=0.6,
    )

    user = recognizer.identify(sample_utterance)

    assert user == "Unknown"


def test_voiceprint_recognizer_identification_fails(
    mock_extractor, mock_repository, sample_utterance
):
    """Test voiceprint recognizer when identification fails."""
    mock_repository.identify.side_effect = RuntimeError("Identification failed")

    recognizer = VoiceprintRecognizer(
        extractor=mock_extractor,
        repository=mock_repository,
        default_user="Unknown",
        threshold=0.6,
    )

    user = recognizer.identify(sample_utterance)

    assert user == "Unknown"


def test_voiceprint_recognizer_enroll(mock_extractor, mock_repository):
    """Test enrolling a new speaker."""
    recognizer = VoiceprintRecognizer(
        extractor=mock_extractor,
        repository=mock_repository,
        default_user="Unknown",
        threshold=0.6,
    )

    audio = np.random.randn(16000).astype(np.float32)
    recognizer.enroll("bob", "Bob", audio, 16000)

    mock_extractor.extract.assert_called_once_with(audio, 16000)
    mock_repository.add_speaker.assert_called_once()


def test_voiceprint_recognizer_enroll_disabled():
    """Test enrolling when voiceprint recognition is disabled."""
    recognizer = VoiceprintRecognizer(
        extractor=None, repository=None, default_user="Unknown"
    )

    audio = np.random.randn(16000).astype(np.float32)

    with pytest.raises(RuntimeError, match="disabled"):
        recognizer.enroll("bob", "Bob", audio, 16000)


def test_voiceprint_recognizer_close(mock_extractor, mock_repository):
    """Test resource cleanup."""
    recognizer = VoiceprintRecognizer(
        extractor=mock_extractor,
        repository=mock_repository,
        default_user="Unknown",
        threshold=0.6,
    )

    recognizer.close()

    mock_extractor.close.assert_called_once()
    mock_repository.close.assert_called_once()


def test_voiceprint_recognizer_close_disabled():
    """Test resource cleanup when disabled."""
    recognizer = VoiceprintRecognizer(
        extractor=None, repository=None, default_user="Unknown"
    )

    # Should not raise exception
    recognizer.close()


def test_voiceprint_recognizer_custom_threshold(mock_extractor, mock_repository, sample_utterance):
    """Test voiceprint recognizer with custom threshold."""
    recognizer = VoiceprintRecognizer(
        extractor=mock_extractor,
        repository=mock_repository,
        default_user="Unknown",
        threshold=0.8,
    )

    recognizer.identify(sample_utterance)

    # Verify threshold is passed to repository
    # The call is: repository.identify(embedding, threshold)
    call_args = mock_repository.identify.call_args
    # Check positional args: (embedding, threshold)
    assert call_args[0][1] == 0.8
