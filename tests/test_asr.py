"""Tests for ASR (Automatic Speech Recognition)."""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from src.voice_assistant.audio.input.asr import ASR


def generate_pcm(sample_rate=16000, duration_s=0.5):
    """Generate short float32 mono PCM (deterministic)."""
    n = int(sample_rate * duration_s)
    t = np.linspace(0, duration_s, n, dtype=np.float32)
    return (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


class TestASR:
    """Unit tests for ASR with mocked faster-whisper."""

    @pytest.fixture
    def mock_whisper_model(self):
        """Mock WhisperModel: transcribe returns (segments_iter, info)."""
        segments = [MagicMock(text=" hello ", start=0.0, end=0.5)]
        info = MagicMock(language="en", language_probability=0.95)
        with patch(
            "src.voice_assistant.audio.input.asr.WhisperModel",
            return_value=MagicMock(
                transcribe=MagicMock(return_value=(iter(segments), info))
            ),
        ) as mock_cls:
            yield mock_cls

    def test_transcribe_returns_text_language_confidence(self, mock_whisper_model):
        """ASR.transcribe returns (text, language, confidence) from model."""
        asr = ASR(model_size="base", device="cpu")
        pcm = generate_pcm()
        text, language, confidence = asr.transcribe(pcm, 16000)
        assert text == "hello"
        assert language == "en"
        assert confidence == 0.95

    def test_transcribe_empty_pcm_returns_empty_result(self, mock_whisper_model):
        """Empty PCM returns empty text and None language/confidence."""
        asr = ASR(model_size="base", device="cpu")
        pcm = np.array([], dtype=np.float32)
        text, language, confidence = asr.transcribe(pcm, 16000)
        assert text == ""
        assert language is None
        assert confidence is None

    def test_transcribe_strips_and_joins_segments(self):
        """Multiple segments are joined with space and stripped."""
        seg1 = MagicMock(text=" foo ", start=0.0, end=0.2)
        seg2 = MagicMock(text=" bar ", start=0.2, end=0.5)
        info = MagicMock(language="zh", language_probability=0.9)
        with patch(
            "src.voice_assistant.audio.input.asr.WhisperModel",
            return_value=MagicMock(
                transcribe=MagicMock(return_value=(iter([seg1, seg2]), info))
            ),
        ):
            asr = ASR(model_size="base", device="cpu")
            text, language, confidence = asr.transcribe(generate_pcm(), 16000)
        assert text == "foo bar"
        assert language == "zh"
        assert confidence == 0.9
