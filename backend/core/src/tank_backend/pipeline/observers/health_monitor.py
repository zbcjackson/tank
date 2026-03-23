"""HealthMonitor — periodic health checker with auto-restart for processor failures."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..bus import Bus, BusMessage

if TYPE_CHECKING:
    from ..builder import Pipeline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthMonitorConfig:
    """Configuration for the HealthMonitor."""

    poll_interval_s: float = 5.0
    stuck_threshold_s: float = 10.0
    max_consecutive_failures: int = 3
    auto_restart_enabled: bool = True
    restart_backoff_base_s: float = 1.0
    restart_backoff_max_s: float = 30.0


class HealthMonitor:
    """Periodically checks pipeline health and triggers auto-restart on failure.

    Runs a background timer thread that polls ``Pipeline.health_snapshot()``
    at a configurable interval. When it detects:
    - A dead consumer thread → posts ``processor_failure`` bus message
    - A stuck queue → posts ``queue_stuck`` bus message
    - Consecutive failures above threshold → schedules processor restart

    Auto-restart uses exponential backoff per processor name.
    """

    def __init__(
        self,
        pipeline: Pipeline,
        bus: Bus,
        config: HealthMonitorConfig | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._bus = bus
        self._config = config or HealthMonitorConfig()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Exponential backoff state: processor_name → (attempts, next_restart_at)
        self._restart_state: dict[str, _RestartState] = {}

    def start(self) -> None:
        """Start the periodic health check thread."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, name="HealthMonitor", daemon=True
        )
        self._thread.start()
        logger.info(
            "HealthMonitor started (interval=%.1fs, auto_restart=%s)",
            self._config.poll_interval_s,
            self._config.auto_restart_enabled,
        )

    def stop(self) -> None:
        """Stop the health check thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._config.poll_interval_s + 1.0)
            self._thread = None
        logger.info("HealthMonitor stopped")

    def _poll_loop(self) -> None:
        """Background loop that runs health checks at a regular interval."""
        while not self._stop_event.is_set():
            try:
                self._check_health()
            except Exception:
                logger.error("HealthMonitor check failed", exc_info=True)
            self._stop_event.wait(timeout=self._config.poll_interval_s)

    def _check_health(self) -> None:
        """Single health check iteration."""
        snapshot = self._pipeline.health_snapshot(self._config.stuck_threshold_s)

        for qh in snapshot.queues:
            if qh.is_stuck:
                self._bus.post(
                    BusMessage(
                        type="queue_stuck",
                        source=qh.name,
                        payload={"size": qh.size, "maxsize": qh.maxsize},
                    )
                )

            if not qh.consumer_alive:
                self._bus.post(
                    BusMessage(
                        type="processor_failure",
                        source=qh.name,
                        payload={"reason": "consumer_dead"},
                    )
                )
                if self._config.auto_restart_enabled:
                    self._maybe_restart(qh.name)

        # Check consecutive failure threshold
        for ph in snapshot.processors:
            if ph.consecutive_failures >= self._config.max_consecutive_failures:
                self._bus.post(
                    BusMessage(
                        type="processor_failure",
                        source=ph.name,
                        payload={
                            "reason": "consecutive_failures",
                            "count": ph.consecutive_failures,
                        },
                    )
                )
                if self._config.auto_restart_enabled:
                    self._maybe_restart(ph.name)

    def _maybe_restart(self, processor_name: str) -> None:
        """Restart a processor if backoff allows it."""
        now = time.monotonic()
        state = self._restart_state.get(processor_name)

        if state is not None and now < state.next_restart_at:
            return  # Still in backoff period

        # Compute next backoff
        attempts = (state.attempts + 1) if state else 1
        backoff = min(
            self._config.restart_backoff_base_s * (2 ** (attempts - 1)),
            self._config.restart_backoff_max_s,
        )
        self._restart_state[processor_name] = _RestartState(
            attempts=attempts,
            next_restart_at=now + backoff,
        )

        logger.warning(
            "Auto-restarting processor %r (attempt %d, next backoff %.1fs)",
            processor_name,
            attempts,
            backoff,
        )

        try:
            # Run async restart in a temporary event loop (we're in a thread)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self._pipeline.restart_processor(processor_name)
                )
            finally:
                loop.close()
        except Exception:
            logger.error(
                "Failed to restart processor %r", processor_name, exc_info=True
            )

    def clear_backoff(self, processor_name: str) -> None:
        """Clear backoff state for a processor (e.g., after manual intervention)."""
        self._restart_state.pop(processor_name, None)


@dataclass
class _RestartState:
    """Tracks restart backoff for a single processor."""

    attempts: int = 0
    next_restart_at: float = 0.0
