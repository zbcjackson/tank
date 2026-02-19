"""Tests for VoiceprintRecognizer."""

import numpy as np
import pytest

from tank_backend.audio.input.segmenter import Utterance
from tank_backend.audio.input.voiceprint import VoiceprintRecognizer


def make_utterance(pcm_len=1600, sample_rate=16000):
    """Create a minimal Utterance."""
    pcm = np.zeros(pcm_len, dtype=np.float32)
    return Utterance(
        pcm=pcm,
        sample_rate=sample_rate,
        started_at_s=0.0,
        ended_at_s=0.1,
    )


class TestVoiceprintRecognizer:
    """Unit tests for default VoiceprintRecognizer."""

    def test_identify_returns_default_user(self):
        """Default implementation returns configured default_user."""
        recognizer = VoiceprintRecognizer(default_user="Unknown")
        utterance = make_utterance()
        assert recognizer.identify(utterance) == "Unknown"

    def test_identify_returns_custom_default_user(self):
        """Custom default_user is returned."""
        recognizer = VoiceprintRecognizer(default_user="Alice")
        utterance = make_utterance()
        assert recognizer.identify(utterance) == "Alice"
