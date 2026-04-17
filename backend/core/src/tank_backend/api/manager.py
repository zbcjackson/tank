"""Connection management for multiple Assistant instances."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ..core.assistant import Assistant

if TYPE_CHECKING:
    from ..audio.input.voiceprint import VoiceprintRecognizer

logger = logging.getLogger("ConnectionManager")


class ConnectionManager:
    """
    Manages active WebSocket connections → Assistant instances.
    Maps ws session_id to Assistant instance.
    Holds a shared VoiceprintRecognizer for the speakers REST API.

    Connections survive brief WebSocket disconnects via an idle timeout.
    A new WebSocket with the same session_id reattaches to the existing
    assistant pipeline instead of creating a new one.
    """

    SESSION_IDLE_TIMEOUT = 30  # seconds

    def __init__(self, app_config: Any = None):
        self._sessions: dict[str, Assistant] = {}
        self._idle_timers: dict[str, asyncio.TimerHandle] = {}
        self._ws_refcount: dict[str, int] = {}
        self._session_lock = asyncio.Lock()
        self._app_config = app_config
        self._voiceprint_recognizer: VoiceprintRecognizer | None = None
        self._init_voiceprint()

    def _init_voiceprint(self) -> None:
        """Initialize shared voiceprint recognizer for the speakers REST API."""
        if self._app_config is None:
            return
        try:
            from ..audio.input.voiceprint_factory import (
                create_disabled_recognizer,
                create_voiceprint_recognizer,
            )

            speaker_cfg = self._app_config.get_feature_config("speaker")

            if not speaker_cfg.enabled or not speaker_cfg.extension:
                self._voiceprint_recognizer = create_disabled_recognizer()
                return

            registry = self._app_config._registry
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

    def get_assistant(self, session_id: str) -> Assistant | None:
        """Retrieve assistant instance for a session."""
        return self._sessions.get(session_id)

    def iter_sessions(self):
        """Iterate over all active (session_id, assistant) pairs."""
        yield from self._sessions.items()

    async def get_or_create_assistant(
        self, session_id: str,
    ) -> tuple[Assistant, bool]:
        """Get existing session or create new one. Returns (assistant, is_new).

        If an existing session is still alive, cancels its idle timer and
        returns it for reattachment. Otherwise creates a fresh session.
        Uses a lock to prevent concurrent reconnects from creating duplicates.
        Increments the WebSocket refcount so we know when all connections
        have detached.
        """
        async with self._session_lock:
            self._cancel_idle_timer(session_id)

            existing = self._sessions.get(session_id)
            if existing and not existing.shutdown_signal.is_set():
                self._ws_refcount[session_id] = (
                    self._ws_refcount.get(session_id, 0) + 1
                )
                logger.debug(
                    f"Session {session_id} refcount: "
                    f"{self._ws_refcount[session_id]}"
                )
                return existing, False

            # Old session is dead or doesn't exist — create fresh
            if existing:
                await self._cleanup_assistant(session_id, existing)

            assistant = Assistant(app_config=self._app_config)
            self._sessions[session_id] = assistant
            self._ws_refcount[session_id] = 1
            await assistant.start()
            logger.info(
                f"Created and started Assistant for session: {session_id}"
            )
            return assistant, True

    def detach_websocket(self, session_id: str) -> None:
        """Decrement WS refcount. Start idle timer only when no WS remains."""
        count = self._ws_refcount.get(session_id, 0) - 1
        if count > 0:
            self._ws_refcount[session_id] = count
            logger.debug(
                f"Session {session_id} refcount: {count} "
                f"(idle timer skipped)"
            )
            return

        self._ws_refcount.pop(session_id, None)
        self._start_idle_timer(session_id)

    def _start_idle_timer(self, session_id: str) -> None:
        """Start countdown to destroy session. Cancelled if client reconnects."""
        self._cancel_idle_timer(session_id)
        loop = asyncio.get_running_loop()
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
        self, session_id: str, assistant: Assistant,
    ) -> None:
        """Stop an assistant and remove it from the session map."""
        self._sessions.pop(session_id, None)
        await assistant.stop()

    async def close_session(self, session_id: str) -> None:
        """Stop and remove assistant instance, cancel any idle timer."""
        self._cancel_idle_timer(session_id)
        self._ws_refcount.pop(session_id, None)
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
        self._ws_refcount.clear()

        ids = list(self._sessions.keys())
        for sid in ids:
            await self.close_session(sid)

        # Close shared voiceprint recognizer
        if self._voiceprint_recognizer:
            self._voiceprint_recognizer.close()
            logger.info("Closed shared voiceprint recognizer")
