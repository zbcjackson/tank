"""Factory for creating voiceprint recognizer instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .voiceprint import VoiceprintRecognizer

if TYPE_CHECKING:
    from ...config.settings import VoiceAssistantConfig

logger = logging.getLogger("VoiceprintFactory")


def _create_disabled_recognizer(config: VoiceAssistantConfig) -> VoiceprintRecognizer:
    """Create a disabled voiceprint recognizer."""
    return VoiceprintRecognizer(
        extractor=None,
        repository=None,
        default_user=config.speaker_default_user,
    )


def create_voiceprint_recognizer(config: VoiceAssistantConfig) -> VoiceprintRecognizer:
    """
    Create a VoiceprintRecognizer instance based on configuration.

    Args:
        config: Voice assistant configuration

    Returns:
        VoiceprintRecognizer instance (enabled or disabled based on config)
    """
    if not config.enable_speaker_id:
        logger.info("Speaker identification disabled by configuration")
        return _create_disabled_recognizer(config)

    try:
        from .embedding_sherpa import SherpaEmbeddingExtractor
        from .repository_sqlite import SQLiteSpeakerRepository

        logger.info("Initializing speaker identification components...")

        # Create embedding extractor
        extractor = SherpaEmbeddingExtractor(
            model_path=config.speaker_model_path,
            num_threads=1,
            provider="cpu",
        )

        # Create speaker repository
        repository = SQLiteSpeakerRepository(db_path=config.speaker_db_path)

        # Create voiceprint recognizer
        recognizer = VoiceprintRecognizer(
            extractor=extractor,
            repository=repository,
            default_user=config.speaker_default_user,
            threshold=config.speaker_threshold,
        )

        logger.info("Speaker identification enabled successfully")
        return recognizer

    except FileNotFoundError as e:
        logger.warning(f"Speaker model not found: {e}")
        logger.warning("Falling back to disabled speaker identification")
        return _create_disabled_recognizer(config)
    except Exception as e:
        logger.error(f"Failed to initialize speaker identification: {e}")
        logger.warning("Falling back to disabled speaker identification")
        return _create_disabled_recognizer(config)
