"""Factory for creating voiceprint recognizer instances."""

from __future__ import annotations

import logging

from .voiceprint import VoiceprintRecognizer

logger = logging.getLogger("VoiceprintFactory")


def create_voiceprint_recognizer(
    extractor: object,
    config: dict,
) -> VoiceprintRecognizer:
    """Create a VoiceprintRecognizer from a pre-built extractor.

    Args:
        extractor: Speaker embedding extractor instance (from plugin).
        config: Slot config dict (db_path, threshold, default_user).

    Returns:
        VoiceprintRecognizer instance.
    """
    from .repository_sqlite import SQLiteSpeakerRepository

    db_path = config.get("db_path", "../data/speakers.db")
    repository = SQLiteSpeakerRepository(db_path=db_path)
    threshold = config.get("threshold", 0.6)
    default_user = config.get("default_user", "Unknown")

    recognizer = VoiceprintRecognizer(
        extractor=extractor,
        repository=repository,
        default_user=default_user,
        threshold=threshold,
    )
    logger.info("Speaker identification enabled")
    return recognizer


def create_disabled_recognizer() -> VoiceprintRecognizer:
    """Create a disabled voiceprint recognizer."""
    return VoiceprintRecognizer(
        extractor=None,
        repository=None,
        default_user="Unknown",
    )
