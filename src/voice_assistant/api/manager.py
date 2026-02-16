"""Session management for multiple Assistant instances."""

from __future__ import annotations

import logging
import asyncio
from typing import Dict, Optional
from pathlib import Path

from ..core.assistant import Assistant
from ..audio.input.types import AudioSourceFactory
from ..audio.output.types import AudioSinkFactory

logger = logging.getLogger("SessionManager")


class SessionManager:
    """
    Manages active voice assistant sessions.
    Maps session_id to Assistant instance.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._sessions: Dict[str, Assistant] = {}
        self._config_path = config_path

    def get_assistant(self, session_id: str) -> Optional[Assistant]:
        """Retrieve assistant instance for a session."""
        return self._sessions.get(session_id)

    def create_assistant(
        self, 
        session_id: str,
        audio_source_factory: AudioSourceFactory,
        audio_sink_factory: AudioSinkFactory
    ) -> Assistant:
        """Create and start a new assistant instance for a session."""
        if session_id in self._sessions:
            logger.warning(f"Session {session_id} already exists. Stopping old instance.")
            self.close_session(session_id)

        assistant = Assistant(
            config_path=self._config_path,
            audio_source_factory=audio_source_factory,
            audio_sink_factory=audio_sink_factory
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
