"""Tests for StreamingVoiceprintRecognizer."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from tank_backend.audio.input.voiceprint import Utterance, VoiceprintRecognizer
from tank_backend.audio.input.voiceprint_streaming import StreamingVoiceprintRecognizer


def make_frame(pcm_len=320, sample_rate=16000):
    """Create a minimal AudioFrame-like object."""
    frame = MagicMock()
    frame.pcm = np.random.randn(pcm_len).astype(np.float32)
    frame.sample_rate = sample_rate
    return frame


@pytest.fixture
def mock_recognizer():
    """Create a mock VoiceprintRecognizer."""
    recognizer = MagicMock(spec=VoiceprintRecognizer)
    recognizer.default_user = "Unknown"
    recognizer.identify.return_value = "alice"
    return recognizer


@pytest.fixture
def streaming(mock_recognizer):
    """Create a StreamingVoiceprintRecognizer with mock."""
    return StreamingVoiceprintRecognizer(mock_recognizer, sample_rate=16000)


class TestStreamingVoiceprintRecognizer:
    def test_identify_and_reset_returns_default_when_no_frames(self, streaming, mock_recognizer):
        """Returns default user when no frames have been accumulated."""
        result = streaming.identify_and_reset()
        assert result == "Unknown"
        mock_recognizer.identify.assert_not_called()

    def test_accumulate_and_identify(self, streaming, mock_recognizer):
        """Accumulates frames and identifies speaker on identify_and_reset."""
        frame1 = make_frame(pcm_len=320)
        frame2 = make_frame(pcm_len=320)

        streaming.accumulate(frame1)
        streaming.accumulate(frame2)

        result = streaming.identify_and_reset()

        assert result == "alice"
        mock_recognizer.identify.assert_called_once()

        # Verify the Utterance passed to identify
        utterance = mock_recognizer.identify.call_args[0][0]
        assert isinstance(utterance, Utterance)
        assert len(utterance.pcm) == 640  # 320 + 320
        assert utterance.sample_rate == 16000

    def test_buffer_resets_after_identify(self, streaming, mock_recognizer):
        """Buffer is cleared after identify_and_reset."""
        streaming.accumulate(make_frame())
        streaming.identify_and_reset()

        # Second call should return default (empty buffer)
        result = streaming.identify_and_reset()
        assert result == "Unknown"
        assert mock_recognizer.identify.call_count == 1  # Only called once

    def test_enroll_delegates_to_recognizer(self, streaming, mock_recognizer):
        """Enroll delegates to underlying recognizer."""
        audio = np.random.randn(16000).astype(np.float32)
        streaming.enroll("bob", "Bob", audio)

        mock_recognizer.enroll.assert_called_once_with("bob", "Bob", audio, 16000)

    def test_close_delegates_to_recognizer(self, streaming, mock_recognizer):
        """Close delegates to underlying recognizer."""
        streaming.close()
        mock_recognizer.close.assert_called_once()

    def test_multiple_utterances(self, streaming, mock_recognizer):
        """Can identify multiple utterances sequentially."""
        mock_recognizer.identify.side_effect = ["alice", "bob"]

        # First utterance
        streaming.accumulate(make_frame(pcm_len=480))
        result1 = streaming.identify_and_reset()
        assert result1 == "alice"

        # Second utterance
        streaming.accumulate(make_frame(pcm_len=640))
        result2 = streaming.identify_and_reset()
        assert result2 == "bob"

        assert mock_recognizer.identify.call_count == 2

        # Verify different audio lengths
        utt1 = mock_recognizer.identify.call_args_list[0][0][0]
        utt2 = mock_recognizer.identify.call_args_list[1][0][0]
        assert len(utt1.pcm) == 480
        assert len(utt2.pcm) == 640
