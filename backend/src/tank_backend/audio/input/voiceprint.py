"""Voiceprint recognition for speaker identification."""

from __future__ import annotations

from .segmenter import Utterance


class VoiceprintRecognizer:
    """
    Identifies speaker from utterance audio.

    Default implementation always returns the configured default user.
    Can be extended with real voiceprint model later.
    """

    def __init__(self, default_user: str = "Unknown"):
        self._default_user = default_user

    def identify(self, utterance: Utterance) -> str:
        """
        Identify speaker from utterance.

        Args:
            utterance: Complete utterance audio segment.

        Returns:
            User identifier (default implementation returns default_user).
        """
        return self._default_user
