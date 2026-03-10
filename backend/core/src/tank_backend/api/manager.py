"""Session management for multiple Assistant instances."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..audio.input.types import AudioSourceFactory
from ..audio.output.types import AudioSinkFactory
from ..config.settings import load_config
from ..core.assistant import Assistant

if TYPE_CHECKING:
    from ..audio.input.voiceprint import VoiceprintRecognizer

logger = logging.getLogger("SessionManager")


class SessionManager:
    """
    Manages active voice assistant sessions.
    Maps session_id to Assistant instance.
    Holds a shared VoiceprintRecognizer for the speakers REST API.
    """

    def __init__(self, config_path: Path | None = None):
        self._sessions: dict[str, Assistant] = {}
        self._config_path = config_path
        self._voiceprint_recognizer: VoiceprintRecognizer | None = None

        # Initialize shared voiceprint recognizer for REST API
        try:
            config = load_config(config_path)
            if config.enable_speaker_id:
                from ..audio.input.voiceprint_factory import (
                    create_disabled_recognizer,
                    create_voiceprint_recognizer,
                )
                from ..plugin import AppConfig
                from ..plugin.manager import PluginManager

                pm = PluginManager()
                registry = pm.load_all()
                app_config = AppConfig(registry=registry)

                speaker_slot = app_config.get_slot_config("speaker")
                if speaker_slot.enabled and speaker_slot.extension:
                    extractor = registry.instantiate(
                        speaker_slot.extension, speaker_slot.config
                    )
                    self._voiceprint_recognizer = create_voiceprint_recognizer(
                        extractor, speaker_slot.config
                    )
                    logger.info("Shared voiceprint recognizer initialized")
                else:
                    self._voiceprint_recognizer = create_disabled_recognizer()
        except Exception as e:
            logger.warning(f"Failed to initialize voiceprint recognizer: {e}")

    def get_voiceprint_recognizer(self) -> VoiceprintRecognizer | None:
        """Get the shared voiceprint recognizer."""
        return self._voiceprint_recognizer

    def get_assistant(self, session_id: str) -> Assistant | None:
        """Retrieve assistant instance for a session."""
        return self._sessions.get(session_id)

    def create_assistant(
        self,
        session_id: str,
        audio_source_factory: AudioSourceFactory,
        audio_sink_factory: AudioSinkFactory,
    ) -> Assistant:
        """Create and start a new assistant instance for a session."""
        if session_id in self._sessions:
            logger.warning(f"Session {session_id} already exists. Stopping old instance.")
            self.close_session(session_id)

        assistant = Assistant(
            config_path=self._config_path,
            audio_source_factory=audio_source_factory,
            audio_sink_factory=audio_sink_factory,
        )
        self._sessions[session_id] = assistant
        assistant.start()
        logger.info(f"Created and started assistant for session: {session_id}")
        return assistant

    def close_session(self, session_id: str):
        """Stop and remove assistant instance."""
        assistant = self._sessions.pop(session_id, None)
        if assistant:
            assistant.stop()
            logger.info(f"Closed session: {session_id}")

    def close_all(self):
        """Stop all active assistants."""
        ids = list(self._sessions.keys())
        for sid in ids:
            self.close_session(sid)

        # Close shared voiceprint recognizer
        if self._voiceprint_recognizer:
            self._voiceprint_recognizer.close()
            logger.info("Closed shared voiceprint recognizer")
