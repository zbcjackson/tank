"""Connection management for multiple Assistant instances."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from ..config.context import AppContext
from ..core.assistant import Assistant

if TYPE_CHECKING:
    from ..audio.input.voiceprint import VoiceprintRecognizer

logger = logging.getLogger("ConnectionManager")


class ConnectionManager:
    """
    Manages active WebSocket connections → Assistant instances.
    Maps ws session_id to Assistant instance.

    Connections survive brief WebSocket disconnects via an idle timeout.
    A new WebSocket with the same session_id reattaches to the existing
    assistant pipeline instead of creating a new one.
    """

    SESSION_IDLE_TIMEOUT = 30  # seconds

    def __init__(self, app_context: AppContext):
        self._sessions: dict[str, Assistant] = {}
        self._idle_timers: dict[str, asyncio.TimerHandle] = {}
        self._ws_refcount: dict[str, int] = {}
        self._session_lock = asyncio.Lock()
        self._app_context = app_context
        self._senders: dict[str, Callable[[str], Awaitable[None]]] = {}
        self._binary_senders: dict[str, Callable[[bytes], Awaitable[None]]] = {}
        self._session_meta: dict[str, dict[str, str]] = {}

    def get_voiceprint_recognizer(self) -> VoiceprintRecognizer | None:
        """Get the shared voiceprint recognizer."""
        return self._app_context.voiceprint_recognizer

    def get_assistant(self, session_id: str) -> Assistant | None:
        """Retrieve assistant instance for a session."""
        return self._sessions.get(session_id)

    def iter_sessions(self):
        """Iterate over all active (session_id, assistant) pairs."""
        yield from self._sessions.items()

    # ── Broadcast ─────────────────────────────────────────────────

    def register_sender(
        self, session_id: str, send_fn: Callable[[str], Awaitable[None]],
    ) -> None:
        """Register a WebSocket send function for broadcast."""
        self._senders[session_id] = send_fn

    def unregister_sender(self, session_id: str) -> None:
        """Remove a WebSocket send function."""
        self._senders.pop(session_id, None)

    # ── Binary senders (audio) ────────────────────────────────────

    def register_binary_sender(
        self, session_id: str, send_fn: Callable[[bytes], Awaitable[None]],
    ) -> None:
        """Register a binary (audio) send function for targeted delivery."""
        self._binary_senders[session_id] = send_fn

    def unregister_binary_sender(self, session_id: str) -> None:
        """Remove a binary send function."""
        self._binary_senders.pop(session_id, None)

    def get_binary_sender(
        self, session_id: str,
    ) -> Callable[[bytes], Awaitable[None]] | None:
        """Get the binary sender for a specific session, or None."""
        return self._binary_senders.get(session_id)

    def get_text_sender(
        self, session_id: str,
    ) -> Callable[[str], Awaitable[None]] | None:
        """Get the JSON text sender for a specific session, or None."""
        return self._senders.get(session_id)

    # ── Session metadata ──────────────────────────────────────────

    def set_session_channel(self, session_id: str, slug: str | None) -> None:
        """Track which channel a session is currently on."""
        meta = self._session_meta.setdefault(session_id, {})
        if slug is None:
            meta.pop("channel_slug", None)
        else:
            meta["channel_slug"] = slug

    def get_session_channel(self, session_id: str) -> str | None:
        """Get the channel slug a session is currently on, or None."""
        return self._session_meta.get(session_id, {}).get("channel_slug")

    async def broadcast(self, message_json: str) -> int:
        """Send a JSON string to all connected WebSocket sessions."""
        sent = 0
        dead: list[str] = []
        for sid, send_fn in list(self._senders.items()):
            try:
                await send_fn(message_json)
                sent += 1
            except Exception:
                logger.debug("Broadcast send failed for session %s", sid)
                dead.append(sid)
        for sid in dead:
            self._senders.pop(sid, None)
        return sent

    async def get_or_create_assistant(
        self, session_id: str,
        *,
        wants_audio_input: bool = True,
        wants_audio_output: bool = True,
    ) -> tuple[Assistant, bool]:
        """Get existing session or create new one. Returns (assistant, is_new).

        If an existing session is still alive, cancels its idle timer and
        returns it for reattachment. Otherwise creates a fresh session.
        Uses a lock to prevent concurrent reconnects from creating duplicates.
        Increments the WebSocket refcount so we know when all connections
        have detached.

        ``wants_audio_input`` / ``wants_audio_output`` only apply when a
        fresh Assistant is built. Reattach reuses the existing Assistant's
        modality choice — callers must not assume the first caller's flags
        match later callers'.
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

            assistant = Assistant(
                app_context=self._app_context,
                wants_audio_input=wants_audio_input,
                wants_audio_output=wants_audio_output,
            )
            self._sessions[session_id] = assistant
            self._ws_refcount[session_id] = 1
            await assistant.start()
            logger.info(
                f"Created and started Assistant for session: {session_id} "
                f"(audio_in={wants_audio_input}, audio_out={wants_audio_output})"
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
        self._session_meta.pop(session_id, None)
        assistant = self._sessions.pop(session_id, None)
        if assistant is None:
            return
        await assistant.stop()
        logger.info(f"Closed session: {session_id}")

    async def close_all(self) -> None:
        """Stop all active assistants and cancel all idle timers."""
        for timer in self._idle_timers.values():
            timer.cancel()
        self._idle_timers.clear()
        self._ws_refcount.clear()

        ids = list(self._sessions.keys())
        for sid in ids:
            await self.close_session(sid)

        recognizer = self._app_context.voiceprint_recognizer
        if recognizer:
            recognizer.close()
            logger.info("Closed shared voiceprint recognizer")
