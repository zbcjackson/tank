"""WorkerInboxObserver — surfaces background worker completions to a conversation.

Phase 2 step 4 of the workflow & orchestration roadmap (see
``backend/ORCHESTRATION.md``).

Subscribes to ``BusMessage(type="worker")`` events posted by
``WorkerSupervisor`` and queues terminal completions
(completed/failed/cancelled/timeout) by ``originating_conversation_id``.

The observer doesn't deliver anything itself — Brain calls
:meth:`drain` at the start of each user turn to pull the queued
completions for its current conversation, then injects them as
synthetic system messages so the LLM sees them in context. This keeps
delivery synchronous to the conversation flow rather than racing TTS.

Voice-mode flush rules (debouncing while VAD is active, post-speech
idle thresholds) are deferred to step 5 — for now the inbox is plain
text-channel friendly.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from ..pipeline.bus import Bus, BusMessage

logger = logging.getLogger(__name__)


_TERMINAL_EVENTS: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "timeout"},
)


@dataclass(frozen=True)
class WorkerCompletion:
    """A terminal worker event ready to surface to a conversation."""

    task_id: str
    agent_def: str
    description: str
    status: str
    output: str
    error: str | None
    originating_channel: str | None

    def to_system_message(self) -> str:
        """Render as a one-liner the LLM can read in context."""
        label = self.description or self.agent_def
        if self.status == "completed":
            body = self.output.strip() or "(no text output)"
            return f"[Worker '{label}' completed: {body}]"
        # failed / cancelled / timeout — surface error text
        detail = self.error or self.status
        return f"[Worker '{label}' {self.status}: {detail}]"


class WorkerInboxObserver:
    """Per-conversation queue for background worker completions.

    Bus delivery is poll-based and runs on the bus thread; the
    inbox is therefore guarded by a lock. ``drain`` is intended to
    be called from the main async loop right before each turn.
    """

    def __init__(self, bus: Bus | None = None) -> None:
        self._lock = threading.Lock()
        self._inbox: dict[str, list[WorkerCompletion]] = {}
        if bus is not None:
            bus.subscribe("worker", self._on_message)

    def _on_message(self, message: BusMessage) -> None:
        payload = message.payload or {}
        event = payload.get("event")
        if event not in _TERMINAL_EVENTS:
            return
        conversation_id = payload.get("originating_conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            return
        completion = WorkerCompletion(
            task_id=str(payload.get("task_id") or ""),
            agent_def=str(payload.get("agent_def") or ""),
            description=str(payload.get("description") or ""),
            status=str(payload.get("status") or event),
            output=str(payload.get("output") or ""),
            error=payload.get("error"),
            originating_channel=payload.get("originating_channel"),
        )
        with self._lock:
            self._inbox.setdefault(conversation_id, []).append(completion)
        logger.debug(
            "WorkerInboxObserver: queued %s for conversation %s (task=%s)",
            event, conversation_id, completion.task_id,
        )

    def drain(self, conversation_id: str) -> list[WorkerCompletion]:
        """Pop all queued completions for ``conversation_id``."""
        with self._lock:
            return self._inbox.pop(conversation_id, [])

    def peek(self, conversation_id: str) -> list[WorkerCompletion]:
        """Return queued completions without removing them."""
        with self._lock:
            return list(self._inbox.get(conversation_id, ()))

    def has_pending(self, conversation_id: str) -> bool:
        with self._lock:
            return bool(self._inbox.get(conversation_id))
