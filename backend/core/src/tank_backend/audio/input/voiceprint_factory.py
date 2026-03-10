"""Factory for creating voiceprint recognizer instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .voiceprint import VoiceprintRecognizer

if TYPE_CHECKING:
    from ...plugin import AppConfig

logger = logging.getLogger("VoiceprintFactory")


def create_voiceprint_recognizer(app_config: AppConfig) -> VoiceprintRecognizer:
    """Create a VoiceprintRecognizer instance based on plugin configuration.

    Args:
        app_config: Application configuration (reads speaker slot from config.yaml)

    Returns:
        VoiceprintRecognizer instance (enabled or disabled based on config)
    """
    try:
        from ...plugin import load_plugin

        slot_config = app_config.get_slot_config("speaker")

        # Slot disabled or absent — return disabled recognizer
        if not slot_config.enabled:
            return _create_disabled_recognizer()

        plugin_cfg = slot_config.config

        # Load the embedding extractor via plugin system
        extractor = load_plugin(slot="speaker", plugin_name=slot_config.plugin, config=plugin_cfg)

        # Repository stays in core — it's storage, not an engine
        from .repository_sqlite import SQLiteSpeakerRepository

        db_path = plugin_cfg.get("db_path", "../data/speakers.db")
        repository = SQLiteSpeakerRepository(db_path=db_path)

        threshold = plugin_cfg.get("threshold", 0.6)
        default_user = plugin_cfg.get("default_user", "Unknown")

        recognizer = VoiceprintRecognizer(
            extractor=extractor,
            repository=repository,
            default_user=default_user,
            threshold=threshold,
        )

        logger.info("Speaker identification enabled via plugin '%s'", slot_config.plugin)
        return recognizer

    except (ValueError, FileNotFoundError, ImportError) as e:
        logger.warning(f"Speaker identification not available: {e}")
        return _create_disabled_recognizer()


def _create_disabled_recognizer() -> VoiceprintRecognizer:
    """Create a disabled voiceprint recognizer."""
    return VoiceprintRecognizer(
        extractor=None,
        repository=None,
        default_user="Unknown",
    )
