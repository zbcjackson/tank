"""Session management for multiple Assistant instances."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..config.settings import load_config
from ..core.assistant import Assistant
from ..core.assistant_v2 import AssistantV2

if TYPE_CHECKING:
    from ..audio.input.types import AudioSourceFactory
    from ..audio.input.voiceprint import VoiceprintRecognizer
    from ..audio.output.types import AudioSinkFactory

logger = logging.getLogger("SessionManager")

AnyAssistant = Assistant | AssistantV2


class SessionManager:
    """
    Manages active voice assistant sessions.
    Maps session_id to Assistant or AssistantV2 instance.
    Holds a shared VoiceprintRecognizer for the speakers REST API.
    """

    def __init__(self, config_path: Path | None = None):
        self._sessions: dict[str, AnyAssistant] = {}
        self._config_path = config_path
        self._voiceprint_recognizer: VoiceprintRecognizer | None = None
        self._init_voiceprint(config_path)

    def _init_voiceprint(self, config_path: Path | None) -> None:
        """Initialize shared voiceprint recognizer for the speakers REST API."""
        try:
            config = load_config(config_path)
            if not config.enable_speaker_id:
                return

            from ..audio.input.voiceprint_factory import (
                create_disabled_recognizer,
                create_voiceprint_recognizer,
            )
            from ..plugin import AppConfig
            from ..plugin.manager import PluginManager

            registry = PluginManager().load_all()
            app_config = AppConfig(registry=registry)
            speaker_cfg = app_config.get_feature_config("speaker")

            if not speaker_cfg.enabled or not speaker_cfg.extension:
                self._voiceprint_recognizer = create_disabled_recognizer()
                return

            extractor = registry.instantiate(
                speaker_cfg.extension, speaker_cfg.config
            )
            self._voiceprint_recognizer = create_voiceprint_recognizer(
                extractor, speaker_cfg.config
            )
            logger.info("Shared voiceprint recognizer initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize voiceprint recognizer: {e}")

    def get_voiceprint_recognizer(self) -> VoiceprintRecognizer | None:
        """Get the shared voiceprint recognizer."""
        return self._voiceprint_recognizer

    def get_assistant(self, session_id: str) -> AnyAssistant | None:
        """Retrieve assistant instance for a session."""
        return self._sessions.get(session_id)

    def create_assistant(
        self,
        session_id: str,
        audio_source_factory: AudioSourceFactory,
        audio_sink_factory: AudioSinkFactory,
    ) -> Assistant:
        """Create and start a new (V1) assistant instance for a session."""
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

    async def create_assistant_v2(self, session_id: str) -> AssistantV2:
        """Create and start a pipeline-based AssistantV2 for a session."""
        if session_id in self._sessions:
            logger.warning(f"Session {session_id} already exists. Stopping old instance.")
            await self.close_session_async(session_id)

        assistant = AssistantV2(config_path=self._config_path)
        self._sessions[session_id] = assistant
        await assistant.start()
        logger.info(f"Created and started AssistantV2 for session: {session_id}")
        return assistant

    def close_session(self, session_id: str) -> None:
        """Stop and remove assistant instance (sync — for V1 Assistant)."""
        assistant = self._sessions.pop(session_id, None)
        if assistant is None:
            return
        if isinstance(assistant, AssistantV2):
            # V2 needs async stop — run in event loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(assistant.stop())
            except RuntimeError:
                asyncio.run(assistant.stop())
        else:
            assistant.stop()
        logger.info(f"Closed session: {session_id}")

    async def close_session_async(self, session_id: str) -> None:
        """Stop and remove assistant instance (async — works for both V1 and V2)."""
        assistant = self._sessions.pop(session_id, None)
        if assistant is None:
            return
        if isinstance(assistant, AssistantV2):
            await assistant.stop()
        else:
            assistant.stop()
        logger.info(f"Closed session: {session_id}")

    def close_all(self) -> None:
        """Stop all active assistants."""
        ids = list(self._sessions.keys())
        for sid in ids:
            self.close_session(sid)

        # Close shared voiceprint recognizer
        if self._voiceprint_recognizer:
            self._voiceprint_recognizer.close()
            logger.info("Closed shared voiceprint recognizer")
