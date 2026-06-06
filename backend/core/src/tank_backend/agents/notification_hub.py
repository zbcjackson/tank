"""NotificationHub — unified proactive event delivery to the ChatAgent.

Phase 3 of the workflow & orchestration roadmap.

Replaces ``WorkerInboxObserver`` with a single component that:
- Subscribes to ``"worker"`` bus events (started + terminal)
- Normalizes terminal events into a ``Notification`` dataclass
- Queues per ``originating_conversation_id``
- Cohort-aware delivery: tracks in-flight workers per conversation,
  delivers only when ALL workers in a cohort reach terminal state
  (or a max-wait timeout fires as a safety net)
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

_WAITING_EVENT: str = "waiting"


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
    settle_seconds: float = 1.0
    max_wait_seconds: float = 60.0
    max_batch_size: int = 10


class NotificationHub:
    """Unified notification queue with cohort-aware proactive delivery.

    Subscribes to bus events, normalizes them, queues per conversation,
    and triggers the Brain to speak proactively when all background
    workers for a conversation have settled.
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
        # Cohort tracking: in-flight worker task_ids per conversation
        self._pending_workers: dict[str, set[str]] = {}
        # Timers
        self._settle_timers: dict[str, asyncio.TimerHandle] = {}
        self._max_wait_timers: dict[str, asyncio.TimerHandle] = {}
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
        """Pop all queued notifications for ``conversation_id``.

        Only clears ``_pending_workers`` if the set is empty (all workers
        done). If workers are still in-flight, keep tracking them so
        subsequent completions still benefit from cohort batching.
        """
        with self._lock:
            items = self._inbox.pop(conversation_id, [])
            pending = self._pending_workers.get(conversation_id)
            if pending is not None and len(pending) == 0:
                del self._pending_workers[conversation_id]
        if items:
            self._cancel_timers(conversation_id)
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
        conversation_id = payload.get("originating_conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            return
        task_id = str(payload.get("task_id") or "")

        # Track worker starts for cohort awareness
        if event == "started":
            with self._lock:
                pending = self._pending_workers.setdefault(conversation_id, set())
                pending.add(task_id)
            logger.info(
                "NotificationHub: tracking worker %s for %s (%d in-flight)",
                task_id, conversation_id, len(pending),
            )
            return

        if event not in _TERMINAL_WORKER_EVENTS and event != _WAITING_EVENT:
            return

        agent_def = str(payload.get("agent_def") or "")
        description = str(payload.get("description") or "")
        label = description or agent_def

        # Handle waiting (question) events — deliver immediately
        if event == _WAITING_EVENT:
            question = str(payload.get("question") or "")
            notification = Notification(
                source="worker",
                event_type="question",
                summary=f"[Worker '{label}' needs your input: {question}]",
                detail=question,
                priority="high",
                conversation_id=conversation_id,
                timestamp=time.time(),
                metadata={
                    "task_id": task_id,
                    "agent_def": agent_def,
                    "description": description,
                    "question": question,
                },
            )
            with self._lock:
                queue = self._inbox.setdefault(conversation_id, [])
                queue.append(notification)

            logger.info(
                "NotificationHub: queued question from %s for %s",
                task_id, conversation_id,
            )

            if self._config.proactive_delivery and self._config.enabled:
                self._schedule_settle_timer(conversation_id)
            return

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
            event_type=str(event),
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

        # Remove from in-flight set and enqueue
        with self._lock:
            pending = self._pending_workers.get(conversation_id)
            if pending is not None:
                pending.discard(task_id)
            cohort_done = pending is not None and len(pending) == 0
            # If we never saw a "started" event (legacy/test path),
            # pending will be None — treat as cohort done.
            if pending is None:
                cohort_done = True
            queue = self._inbox.setdefault(notification.conversation_id, [])
            queue.append(notification)
            queue_len = len(queue)

        logger.info(
            "NotificationHub: queued %s/%s for %s (queue_len=%d, cohort_done=%s)",
            notification.source, notification.event_type,
            notification.conversation_id, queue_len, cohort_done,
        )

        if not self._config.proactive_delivery or not self._config.enabled:
            return

        if cohort_done:
            self._schedule_settle_timer(conversation_id)
        else:
            # Workers still in-flight — ensure max-wait timer is running
            self._ensure_max_wait_timer(conversation_id)

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
        with self._lock:
            queue = self._inbox.setdefault(notification.conversation_id, [])
            queue.append(notification)

        if not self._config.proactive_delivery or not self._config.enabled:
            return

        # Jobs don't participate in worker cohorts — deliver after settle
        self._schedule_settle_timer(conversation_id)

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _schedule_settle_timer(self, conversation_id: str) -> None:
        """Schedule delivery after a short settle pause."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def _schedule_on_loop() -> None:
            existing = self._settle_timers.pop(conversation_id, None)
            if existing is not None:
                existing.cancel()
            handle = loop.call_later(
                self._config.settle_seconds,
                self._on_settle_fire,
                conversation_id,
            )
            self._settle_timers[conversation_id] = handle

        asyncio.run_coroutine_threadsafe(
            _wrap_sync(_schedule_on_loop), loop,
        )

    def _ensure_max_wait_timer(self, conversation_id: str) -> None:
        """Set a max-wait timer if one isn't already running."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def _schedule_on_loop() -> None:
            if conversation_id in self._max_wait_timers:
                return
            handle = loop.call_later(
                self._config.max_wait_seconds,
                self._on_max_wait_fire,
                conversation_id,
            )
            self._max_wait_timers[conversation_id] = handle

        asyncio.run_coroutine_threadsafe(
            _wrap_sync(_schedule_on_loop), loop,
        )

    def _cancel_timers(self, conversation_id: str) -> None:
        """Cancel all timers for a conversation."""
        loop = self._loop
        if loop is None:
            return
        handle = self._settle_timers.pop(conversation_id, None)
        if handle is not None:
            handle.cancel()
        handle = self._max_wait_timers.pop(conversation_id, None)
        if handle is not None:
            handle.cancel()

    def _on_settle_fire(self, conversation_id: str) -> None:
        """Called on the event loop when the settle timer expires."""
        self._settle_timers.pop(conversation_id, None)

        if not self.has_pending(conversation_id):
            return

        # Cancel max-wait since we're delivering now
        handle = self._max_wait_timers.pop(conversation_id, None)
        if handle is not None:
            handle.cancel()

        loop = self._loop
        if loop is not None:
            asyncio.ensure_future(
                self._inject_notification_turn(conversation_id), loop=loop,
            )

    def _on_max_wait_fire(self, conversation_id: str) -> None:
        """Safety net: deliver whatever we have after max_wait_seconds."""
        self._max_wait_timers.pop(conversation_id, None)

        if not self.has_pending(conversation_id):
            return

        # Cancel settle timer if pending
        handle = self._settle_timers.pop(conversation_id, None)
        if handle is not None:
            handle.cancel()

        # Clear pending workers — we're delivering regardless
        with self._lock:
            self._pending_workers.pop(conversation_id, None)

        logger.info(
            "NotificationHub: max-wait fired for %s, delivering partial batch",
            conversation_id,
        )

        loop = self._loop
        if loop is not None:
            asyncio.ensure_future(
                self._inject_notification_turn(conversation_id), loop=loop,
            )

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

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
                # Re-schedule settle timer for later
                self._schedule_settle_timer(conversation_id)
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
