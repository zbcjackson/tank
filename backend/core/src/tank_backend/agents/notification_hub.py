"""NotificationHub — unified proactive event delivery to the ChatAgent.

Phase 3 of the workflow & orchestration roadmap.

Replaces ``WorkerInboxObserver`` with a single component that:
- Subscribes to ``"worker"`` (terminal) and ``"job_delivery"`` bus events
- Normalizes each into a ``Notification`` dataclass
- Queues per ``originating_conversation_id``
- Debounces: waits ``debounce_seconds`` after the first event, then fires
- Proactive delivery: injects a synthetic ``BrainInputEvent`` into the
  pipeline when the brain is idle, triggering a notification turn
- Passive fallback: Brain calls ``drain()`` at the start of each user turn

Thread safety: bus callbacks run on the poll thread; timer callbacks run
on the asyncio event loop via ``asyncio.run_coroutine_threadsafe``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..pipeline.bus import Bus, BusMessage

if TYPE_CHECKING:
    from ..pipeline import Pipeline

logger = logging.getLogger(__name__)

_TERMINAL_WORKER_EVENTS: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "timeout"},
)


@dataclass(frozen=True)
class Notification:
    """A normalized event ready to surface to a conversation."""

    source: str
    event_type: str
    summary: str
    detail: str
    priority: str
    conversation_id: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_system_message(self) -> str:
        """Render as a one-liner the LLM can read in context."""
        return self.summary


@dataclass(frozen=True)
class NotificationHubConfig:
    """Configuration for the NotificationHub."""

    enabled: bool = True
    proactive_delivery: bool = True
    debounce_seconds: float = 3.0
    max_batch_size: int = 10


class NotificationHub:
    """Unified notification queue with proactive delivery.

    Subscribes to bus events, normalizes them, queues per conversation,
    and optionally triggers the Brain to speak proactively.
    """

    def __init__(
        self,
        bus: Bus,
        config: NotificationHubConfig | None = None,
    ) -> None:
        self._bus = bus
        self._config = config or NotificationHubConfig()
        self._lock = threading.Lock()
        self._inbox: dict[str, list[Notification]] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pipeline: Pipeline | None = None
        self._brain_idle_event: asyncio.Event | None = None
        self._conversation_id_fn: Any = None

        bus.subscribe("worker", self._on_worker_event)
        bus.subscribe("job_delivery", self._on_job_delivery)

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def set_pipeline(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    def set_brain_idle_event(self, event: asyncio.Event) -> None:
        self._brain_idle_event = event

    def set_conversation_id_fn(self, fn: Any) -> None:
        """Set a callable that returns the current conversation_id for the session."""
        self._conversation_id_fn = fn

    # ------------------------------------------------------------------
    # Public drain API (called by Brain)
    # ------------------------------------------------------------------

    def drain(self, conversation_id: str) -> list[Notification]:
        """Pop all queued notifications for ``conversation_id``."""
        with self._lock:
            items = self._inbox.pop(conversation_id, [])
        if items:
            self._cancel_timer(conversation_id)
        return items

    def has_pending(self, conversation_id: str) -> bool:
        with self._lock:
            return bool(self._inbox.get(conversation_id))

    # ------------------------------------------------------------------
    # Bus event handlers (run on bus poll thread)
    # ------------------------------------------------------------------

    def _on_worker_event(self, message: BusMessage) -> None:
        payload = message.payload or {}
        event = payload.get("event")
        if event not in _TERMINAL_WORKER_EVENTS:
            return
        conversation_id = payload.get("originating_conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            return

        task_id = str(payload.get("task_id") or "")
        agent_def = str(payload.get("agent_def") or "")
        description = str(payload.get("description") or "")
        status = str(payload.get("status") or event)
        output = str(payload.get("output") or "")
        error = payload.get("error")

        label = description or agent_def
        if status == "completed":
            body = output.strip() or "(no text output)"
            summary = f"[Worker '{label}' completed: {body}]"
        else:
            detail_text = error or status
            summary = f"[Worker '{label}' {status}: {detail_text}]"

        notification = Notification(
            source="worker",
            event_type=event,
            summary=summary,
            detail=output if status == "completed" else (error or ""),
            priority="normal",
            conversation_id=conversation_id,
            timestamp=time.time(),
            metadata={
                "task_id": task_id,
                "agent_def": agent_def,
                "description": description,
                "status": status,
            },
        )
        self._enqueue(notification)

    def _on_job_delivery(self, message: BusMessage) -> None:
        payload = message.payload or {}
        job_name = payload.get("job_name", "")
        run_id = payload.get("run_id", "")
        output_path = payload.get("output_path", "")
        channels = payload.get("channels", [])

        # Job deliveries target the current active conversation for this
        # assistant. Use the conversation_id_fn if set.
        conversation_id = ""
        if self._conversation_id_fn is not None:
            conversation_id = self._conversation_id_fn() or ""
        if not conversation_id:
            return

        summary = f"[Job '{job_name}' delivered (run {run_id}): output at {output_path}]"
        if channels:
            summary = f"[Job '{job_name}' delivered to {', '.join(channels)} (run {run_id})]"

        notification = Notification(
            source="job",
            event_type="delivered",
            summary=summary,
            detail=f"Job '{job_name}' completed. Output: {output_path}",
            priority="normal",
            conversation_id=conversation_id,
            timestamp=time.time(),
            metadata={
                "job_name": job_name,
                "run_id": run_id,
                "output_path": output_path,
                "channels": channels,
            },
        )
        self._enqueue(notification)

    # ------------------------------------------------------------------
    # Internal queuing + timer
    # ------------------------------------------------------------------

    def _enqueue(self, notification: Notification) -> None:
        with self._lock:
            queue = self._inbox.setdefault(notification.conversation_id, [])
            queue.append(notification)
            queue_len = len(queue)

        logger.debug(
            "NotificationHub: queued %s/%s for %s (queue_len=%d)",
            notification.source, notification.event_type,
            notification.conversation_id, queue_len,
        )

        if not self._config.proactive_delivery or not self._config.enabled:
            return

        # Schedule or reset debounce timer
        self._schedule_timer(notification.conversation_id)

    def _schedule_timer(self, conversation_id: str) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def _schedule_on_loop() -> None:
            # Cancel existing timer for this conversation
            existing = self._timers.pop(conversation_id, None)
            if existing is not None:
                existing.cancel()
            handle = loop.call_later(
                self._config.debounce_seconds,
                self._on_timer_fire,
                conversation_id,
            )
            self._timers[conversation_id] = handle

        asyncio.run_coroutine_threadsafe(
            _wrap_sync(_schedule_on_loop), loop,
        )

    def _cancel_timer(self, conversation_id: str) -> None:
        loop = self._loop
        if loop is None:
            return
        handle = self._timers.pop(conversation_id, None)
        if handle is not None:
            handle.cancel()

    def _on_timer_fire(self, conversation_id: str) -> None:
        """Called on the event loop when the debounce timer expires."""
        self._timers.pop(conversation_id, None)

        # Check if there are still pending notifications
        if not self.has_pending(conversation_id):
            return

        # Schedule the injection (may need to wait for brain idle)
        loop = self._loop
        if loop is not None:
            asyncio.ensure_future(
                self._inject_notification_turn(conversation_id), loop=loop,
            )

    async def _inject_notification_turn(self, conversation_id: str) -> None:
        """Wait for brain idle, then inject a notification BrainInputEvent."""
        if self._brain_idle_event is not None:
            try:
                await asyncio.wait_for(self._brain_idle_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "NotificationHub: brain not idle after 30s, deferring for %s",
                    conversation_id,
                )
                # Re-schedule for later
                self._schedule_timer(conversation_id)
                return

        # Double-check: notifications may have been drained by a user turn
        if not self.has_pending(conversation_id):
            return

        if self._pipeline is None:
            return

        from ..core.events import BrainInputEvent, InputType

        self._pipeline.push_at(
            "brain",
            BrainInputEvent(
                type=InputType.SYSTEM,
                text="__notification__",
                user="system",
                language=None,
                confidence=None,
                metadata={"conversation_id": conversation_id},
            ),
        )
        logger.info(
            "NotificationHub: injected notification turn for %s",
            conversation_id,
        )


async def _wrap_sync(fn: Any) -> None:
    """Wrap a sync function as a coroutine for run_coroutine_threadsafe."""
    fn()
