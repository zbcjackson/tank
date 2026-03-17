"""Session management for multiple AssistantV2 instances."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..config.settings import load_config
from ..core.assistant_v2 import AssistantV2

if TYPE_CHECKING:
    from ..audio.input.voiceprint import VoiceprintRecognizer

logger = logging.getLogger("SessionManager")


class SessionManager:
    """
    Manages active voice assistant sessions.
    Maps session_id to AssistantV2 instance.
    Holds a shared VoiceprintRecognizer for the speakers REST API.

    Sessions survive brief WebSocket disconnects via an idle timeout.
    A new WebSocket with the same session_id reattaches to the existing
    assistant pipeline instead of creating a new one.
    """

    SESSION_IDLE_TIMEOUT = 30  # seconds

    def __init__(self, config_path: Path | None = None):
        self._sessions: dict[str, AssistantV2] = {}
        self._idle_timers: dict[str, asyncio.TimerHandle] = {}
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

    def get_assistant(self, session_id: str) -> AssistantV2 | None:
        """Retrieve assistant instance for a session."""
        return self._sessions.get(session_id)

    async def get_or_create_assistant(
        self, session_id: str,
    ) -> tuple[AssistantV2, bool]:
        """Get existing session or create new one. Returns (assistant, is_new).

        If an existing session is still alive, cancels its idle timer and
        returns it for reattachment. Otherwise creates a fresh session.
        """
        self._cancel_idle_timer(session_id)

        existing = self._sessions.get(session_id)
        if existing and not existing.shutdown_signal.is_set():
            return existing, False

        # Old session is dead or doesn't exist — create fresh
        if existing:
            await self._cleanup_assistant(session_id, existing)

        assistant = AssistantV2(config_path=self._config_path)
        self._sessions[session_id] = assistant
        await assistant.start()
        logger.info(f"Created and started AssistantV2 for session: {session_id}")
        return assistant, True

    async def create_assistant(self, session_id: str) -> AssistantV2:
        """Create and start a pipeline-based AssistantV2 for a session."""
        if session_id in self._sessions:
            logger.warning(f"Session {session_id} already exists. Stopping old instance.")
            await self.close_session(session_id)

        assistant = AssistantV2(config_path=self._config_path)
        self._sessions[session_id] = assistant
        await assistant.start()
        logger.info(f"Created and started AssistantV2 for session: {session_id}")
        return assistant

    def start_idle_timer(self, session_id: str) -> None:
        """Start countdown to destroy session. Cancelled if client reconnects."""
        self._cancel_idle_timer(session_id)
        loop = asyncio.get_event_loop()
        self._idle_timers[session_id] = loop.call_later(
            self.SESSION_IDLE_TIMEOUT,
            lambda: asyncio.ensure_future(self.close_session(session_id)),
        )
        logger.info(
            f"Idle timer started for {session_id} ({self.SESSION_IDLE_TIMEOUT}s)"
        )

    def _cancel_idle_timer(self, session_id: str) -> None:
        """Cancel a pending idle timer for the given session."""
        timer = self._idle_timers.pop(session_id, None)
        if timer:
            timer.cancel()
            logger.debug(f"Idle timer cancelled for {session_id}")

    async def _cleanup_assistant(
        self, session_id: str, assistant: AssistantV2,
    ) -> None:
        """Stop an assistant and remove it from the session map."""
        self._sessions.pop(session_id, None)
        await assistant.stop()

    async def close_session(self, session_id: str) -> None:
        """Stop and remove assistant instance, cancel any idle timer."""
        self._cancel_idle_timer(session_id)
        assistant = self._sessions.pop(session_id, None)
        if assistant is None:
            return
        await assistant.stop()
        logger.info(f"Closed session: {session_id}")

    async def close_all(self) -> None:
        """Stop all active assistants and cancel all idle timers."""
        # Cancel all idle timers first
        for timer in self._idle_timers.values():
            timer.cancel()
        self._idle_timers.clear()

        ids = list(self._sessions.keys())
        for sid in ids:
            await self.close_session(sid)

        # Close shared voiceprint recognizer
        if self._voiceprint_recognizer:
            self._voiceprint_recognizer.close()
            logger.info("Closed shared voiceprint recognizer")
