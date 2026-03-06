"""Streaming voiceprint recognition adapter for StreamingPerception."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .mic import AudioFrame
    from .voiceprint import VoiceprintRecognizer

logger = logging.getLogger("StreamingVoiceprintRecognizer")


class StreamingVoiceprintRecognizer:
    """
    Adapter for VoiceprintRecognizer that works with streaming audio frames.

    Accumulates audio frames during an utterance, then identifies the speaker
    when the utterance is complete (on final transcription).
    """

    def __init__(self, recognizer: VoiceprintRecognizer, sample_rate: int = 16000):
        """
        Initialize streaming voiceprint recognizer.

        Args:
            recognizer: Underlying VoiceprintRecognizer instance
            sample_rate: Audio sample rate in Hz
        """
        self._recognizer = recognizer
        self._sample_rate = sample_rate
        self._audio_buffer: list[np.ndarray] = []

    def accumulate(self, frame: AudioFrame) -> None:
        """
        Accumulate audio frame for later identification.

        Args:
            frame: Audio frame to accumulate
        """
        self._audio_buffer.append(frame.pcm)

    def reset(self) -> None:
        """Discard accumulated audio without running identification."""
        self._audio_buffer.clear()

    def identify_and_reset(self) -> str:
        """
        Identify speaker from accumulated audio, then reset buffer.

        Returns:
            User identifier (user_id or default_user if no match)
        """
        if not self._audio_buffer:
            return self._recognizer.default_user

        # Concatenate all accumulated frames
        audio = np.concatenate(self._audio_buffer)

        # Create Utterance for voiceprint identification
        from .voiceprint import Utterance

        utterance = Utterance(
            pcm=audio,
            sample_rate=self._sample_rate,
            started_at_s=0.0,
            ended_at_s=len(audio) / self._sample_rate,
        )

        # Identify speaker
        user = self._recognizer.identify(utterance)

        # Reset buffer for next utterance
        self._audio_buffer.clear()

        return user

    def enroll(self, user_id: str, name: str, audio: np.ndarray) -> None:
        """
        Enroll a new speaker or add embedding to existing speaker.

        Args:
            user_id: Unique user identifier
            name: Display name
            audio: Audio samples (float32)

        Raises:
            RuntimeError: If voiceprint recognition is disabled
        """
        self._recognizer.enroll(user_id, name, audio, self._sample_rate)

    def close(self) -> None:
        """Release resources."""
        self._recognizer.close()
