"""Voiceprint recognition for speaker identification."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .embedding import SpeakerEmbeddingExtractor
from .repository import SpeakerRepository

logger = logging.getLogger("VoiceprintRecognizer")


@dataclass
class Utterance:
    """Complete utterance audio segment."""

    pcm: np.ndarray  # full utterance audio float32
    sample_rate: int
    started_at_s: float
    ended_at_s: float


class VoiceprintRecognizer:
    """
    Identifies speaker from utterance audio.

    Coordinates between embedding extractor and speaker repository.
    Falls back to default_user if speaker identification is disabled or fails.
    """

    def __init__(
        self,
        extractor: SpeakerEmbeddingExtractor | None = None,
        repository: SpeakerRepository | None = None,
        default_user: str = "Unknown",
        threshold: float = 0.6,
    ):
        """
        Initialize voiceprint recognizer.

        Args:
            extractor: Speaker embedding extractor (None = disabled)
            repository: Speaker repository (None = disabled)
            default_user: Default user when identification fails or is disabled
            threshold: Minimum cosine similarity for identification (0.0-1.0)
        """
        self._extractor = extractor
        self._repository = repository
        self._default_user = default_user
        self._threshold = threshold
        self._enabled = extractor is not None and repository is not None

        if self._enabled:
            logger.info(f"Voiceprint recognition enabled (threshold={threshold})")
        else:
            logger.info("Voiceprint recognition disabled (using default user)")

    @property
    def default_user(self) -> str:
        """Default user when identification fails or is disabled."""
        return self._default_user

    @property
    def enabled(self) -> bool:
        """Whether voiceprint recognition is enabled."""
        return self._enabled

    @property
    def repository(self) -> SpeakerRepository | None:
        """Speaker repository (None if disabled)."""
        return self._repository

    def identify(self, utterance: Utterance) -> str:
        """
        Identify speaker from utterance.

        Args:
            utterance: Complete utterance audio segment.

        Returns:
            User identifier (user_id or default_user if no match).
        """
        if not self._enabled:
            return self._default_user

        try:
            # Extract embedding
            embedding = self._extractor.extract(utterance.pcm, utterance.sample_rate)

            # Identify speaker
            user_id = self._repository.identify(embedding, self._threshold)

            return user_id if user_id else self._default_user

        except Exception as e:
            logger.warning(f"Speaker identification failed: {e}")
            return self._default_user

    def enroll(self, user_id: str, name: str, audio: np.ndarray, sample_rate: int) -> None:
        """
        Enroll a new speaker or add embedding to existing speaker.

        Args:
            user_id: Unique user identifier
            name: Display name
            audio: Audio samples (float32)
            sample_rate: Sample rate in Hz

        Raises:
            RuntimeError: If voiceprint recognition is disabled
        """
        if not self._enabled:
            raise RuntimeError("Voiceprint recognition is disabled")

        embedding = self._extractor.extract(audio, sample_rate)
        self._repository.add_speaker(user_id, name, embedding)
        logger.info(f"Enrolled speaker: {user_id} ({name})")

    def close(self) -> None:
        """Release resources."""
        if self._extractor:
            self._extractor.close()
        if self._repository:
            self._repository.close()
