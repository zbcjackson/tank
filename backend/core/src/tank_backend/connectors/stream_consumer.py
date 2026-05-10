"""StreamConsumer — coalesce Bus ``ui_message`` deltas into platform sends.

Brain emits a streaming reply as many small ``DisplayMessage(is_final=False)``
events sharing one ``msg_id``, followed by a single
``DisplayMessage(is_final=True, text="")``. For chat platforms we need to
decide *how* to surface that stream:

- **Edit transport** (``capabilities.supports_edits=True``): send one
  message on the first token, then periodically edit it as more tokens
  accumulate, and send a final edit when the stream completes. This
  feels "live" while respecting platform edit-rate limits.
- **Final-only** (``capabilities.supports_edits=False``): buffer the
  whole reply, send once on completion. Used for platforms like WeChat
  that don't support edits.

Threading: Bus delivery is synchronous (callback runs under
``bus.poll()``), but connector sends are async. This class captures the
ambient event loop at construction and schedules work via
``run_coroutine_threadsafe`` — safe whether the callback fires on the
app thread or a different one.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..core.events import DisplayMessage, UpdateType

if TYPE_CHECKING:
    from ..pipeline.bus import BusMessage
    from .base import Connector, Identity

logger = logging.getLogger(__name__)


@dataclass
class _MessageState:
    """Per-``msg_id`` streaming state."""

    buffer: str = ""                      # accumulated text
    platform_message_id: str | None = None  # id returned by first send()
    last_edit_at: float = 0.0             # monotonic seconds
    last_sent_text: str = ""              # text we last pushed to platform
    in_flight: bool = False               # an async send/edit is outstanding
    finalized: bool = False               # is_final=True already seen
    pending_final_edit: bool = False      # need one more edit after in-flight returns
    subsequent_messages: list[str] = field(default_factory=list)


class StreamConsumer:
    """Turn Bus ``ui_message`` events into connector sends/edits.

    Create one per ``(Assistant, Identity)`` pairing. Subscribe
    ``on_ui_message`` to the Assistant's Bus. The consumer handles
    everything else — message IDs, buffering, rate-limited edits, final
    delivery.
    """

    def __init__(
        self,
        connector: Connector,
        identity: Identity,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._connector = connector
        self._identity = identity
        self._capabilities = connector.capabilities
        # Capture an event loop reference. Prefer the running loop when one
        # is available; fall back to the caller-supplied loop for tests.
        if loop is not None:
            self._loop = loop
        else:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:  # pragma: no cover — tests should pass loop=
                self._loop = asyncio.new_event_loop()
        self._max_length = self._capabilities.max_message_length
        self._min_edit_interval_s = self._capabilities.edit_min_interval_ms / 1000.0
        self._supports_edits = self._capabilities.supports_edits
        self._states: dict[str, _MessageState] = {}

    # ── Bus subscription entry point ────────────────────────────────

    def on_ui_message(self, message: BusMessage) -> None:
        """Sync Bus handler. Dispatches async work to the captured loop."""
        payload = message.payload
        if not isinstance(payload, DisplayMessage):
            return  # ignore SignalMessage, metric events, etc.
        if payload.is_user:
            return  # never echo user input back to the platform
        if payload.update_type is not UpdateType.TEXT:
            return  # skip THOUGHT, TOOL, APPROVAL — those are UI-only
        if payload.msg_id is None:
            return  # defensive; Brain always sets msg_id

        state = self._states.setdefault(payload.msg_id, _MessageState())
        # Tokens carry deltas; DisplayMessage.text on the final event is empty.
        if payload.text:
            state.buffer += payload.text

        if payload.is_final:
            state.finalized = True

        # Schedule the actual send/edit on the loop.
        asyncio.run_coroutine_threadsafe(
            self._flush(payload.msg_id), self._loop,
        )

    # ── Internal send coordinator ──────────────────────────────────

    async def _flush(self, msg_id: str) -> None:
        """Decide whether to send/edit now for ``msg_id``."""
        state = self._states.get(msg_id)
        if state is None:
            return

        if state.in_flight:
            # A send/edit is already going; mark so we edit again once it
            # settles (covers the "more tokens arrived while we were
            # sending" case).
            if state.finalized or self._supports_edits:
                state.pending_final_edit = True
            return

        # Nothing to do if buffer is identical to what we last sent,
        # unless we need to finalize.
        if state.buffer == state.last_sent_text and not state.finalized:
            return

        # Final-only transport: only emit once, at completion.
        if not self._supports_edits:
            if not state.finalized:
                return
            await self._send_final_only(msg_id, state)
            return

        # Edit transport.
        if state.platform_message_id is None:
            # First emission for this msg_id.
            await self._send_initial(msg_id, state)
        else:
            # Subsequent edit — respect rate limit unless we're finalizing.
            now = time.monotonic()
            elapsed = now - state.last_edit_at
            if not state.finalized and elapsed < self._min_edit_interval_s:
                # Too soon; schedule a follow-up to edit once the window closes.
                remaining = self._min_edit_interval_s - elapsed
                self._loop.call_later(
                    remaining,
                    lambda: asyncio.run_coroutine_threadsafe(
                        self._flush(msg_id), self._loop,
                    ),
                )
                return
            await self._send_edit(msg_id, state)

    async def _send_initial(self, msg_id: str, state: _MessageState) -> None:
        """Issue the first ``connector.send()`` for a streaming message."""
        state.in_flight = True
        text = self._truncate(state.buffer)
        snapshot = state.buffer
        try:
            result = await self._connector.send(
                identity=self._identity,
                text=text,
            )
        except Exception:
            logger.exception(
                "StreamConsumer: send() raised for msg_id=%s on %s",
                msg_id, self._connector.instance_name,
            )
            state.in_flight = False
            return

        state.in_flight = False
        if not result.ok:
            logger.warning(
                "StreamConsumer: send() failed for msg_id=%s on %s: %s",
                msg_id, self._connector.instance_name, result.error,
            )
            return

        state.platform_message_id = result.message_id
        state.last_sent_text = snapshot
        state.last_edit_at = time.monotonic()

        # If more tokens arrived while we were sending, or the stream
        # finished during the flight, re-enter flush to edit/finalize.
        if state.pending_final_edit or state.buffer != snapshot or state.finalized:
            state.pending_final_edit = False
            asyncio.run_coroutine_threadsafe(self._flush(msg_id), self._loop)

    async def _send_edit(self, msg_id: str, state: _MessageState) -> None:
        """Issue a ``connector.edit()`` with the latest accumulated text."""
        if state.platform_message_id is None:
            return  # can't edit without a message id

        state.in_flight = True
        snapshot = state.buffer
        text = self._truncate(snapshot)
        try:
            result = await self._connector.edit(
                identity=self._identity,
                message_id=state.platform_message_id,
                text=text,
            )
        except Exception:
            logger.exception(
                "StreamConsumer: edit() raised for msg_id=%s on %s",
                msg_id, self._connector.instance_name,
            )
            state.in_flight = False
            return

        state.in_flight = False
        if not result.ok:
            logger.warning(
                "StreamConsumer: edit() failed for msg_id=%s on %s: %s",
                msg_id, self._connector.instance_name, result.error,
            )
            return

        state.last_sent_text = snapshot
        state.last_edit_at = time.monotonic()

        if state.pending_final_edit or state.buffer != snapshot:
            state.pending_final_edit = False
            asyncio.run_coroutine_threadsafe(self._flush(msg_id), self._loop)

    async def _send_final_only(self, msg_id: str, state: _MessageState) -> None:
        """Platforms without edit support: one send, at the end."""
        if state.last_sent_text:
            return  # already sent once (defensive)

        state.in_flight = True
        snapshot = state.buffer or ""
        text = self._truncate(snapshot)
        if not text:
            # Empty reply — nothing to send.
            state.in_flight = False
            state.last_sent_text = snapshot
            return

        try:
            result = await self._connector.send(
                identity=self._identity,
                text=text,
            )
        except Exception:
            logger.exception(
                "StreamConsumer: final-only send() raised for msg_id=%s", msg_id,
            )
            state.in_flight = False
            return

        state.in_flight = False
        state.last_sent_text = snapshot
        if result.ok:
            state.platform_message_id = result.message_id

    # ── Helpers ────────────────────────────────────────────────────

    def _truncate(self, text: str) -> str:
        """Apply the connector's ``max_message_length``.

        Naive truncation today; Phase 3 can split long replies across
        multiple messages when we have real platform behaviors to test
        against.
        """
        if self._max_length <= 0 or len(text) <= self._max_length:
            return text
        return text[: self._max_length - 1] + "…"
