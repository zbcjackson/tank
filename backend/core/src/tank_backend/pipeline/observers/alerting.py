"""AlertingObserver — detects anomalies and dispatches alerts."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..bus import Bus, BusMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertThresholds:
    """Configurable thresholds for anomaly detection."""

    latency_spike_multiplier: float = 2.0
    latency_spike_consecutive: int = 5
    error_rate_threshold: float = 0.10
    error_rate_window_s: float = 300.0
    queue_saturation_pct: float = 0.80
    queue_saturation_duration_s: float = 30.0
    stuck_approval_timeout_s: float = 300.0
    alert_cooldown_s: float = 60.0


@dataclass(frozen=True)
class Alert:
    """Immutable alert record."""

    alert_type: str
    severity: str  # "warning", "critical"
    message: str
    source: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class AlertingObserver:
    """Detects anomalies from bus messages and posts alert bus messages.

    Subscribes to: ``asr_result``, ``llm_latency``, ``tts_finished``,
    ``queue_stuck``, ``processor_failure``.
    Posts: ``BusMessage(type="alert", payload=Alert)``.

    Implements cooldown per alert type to prevent flooding.
    """

    def __init__(
        self,
        bus: Bus,
        thresholds: AlertThresholds | None = None,
    ) -> None:
        self._bus = bus
        self._thresholds = thresholds or AlertThresholds()
        self._lock = threading.Lock()

        # Latency tracking (sliding window of last 50 e2e latencies)
        self._latency_history: deque[float] = deque(maxlen=50)
        self._consecutive_spikes: int = 0

        # Error tracking (timestamps of recent errors)
        self._error_timestamps: deque[float] = deque(maxlen=200)
        self._turn_timestamps: deque[float] = deque(maxlen=200)

        # Queue saturation tracking: queue_name → first_saturated_at
        self._saturation_start: dict[str, float] = {}

        # Alert cooldown: alert_type → last_fired_at
        self._last_alert_at: dict[str, float] = {}

        # Alert history for snapshot
        self._alerts: list[Alert] = []

        # Subscribe to relevant bus messages
        bus.subscribe("asr_result", self._on_message)
        bus.subscribe("llm_latency", self._on_message)
        bus.subscribe("tts_finished", self._on_message)
        bus.subscribe("queue_stuck", self._on_message)
        bus.subscribe("processor_failure", self._on_message)
        bus.subscribe("playback_started", self._on_message)

    def _on_message(self, message: BusMessage) -> None:
        with self._lock:
            if message.type == "asr_result":
                self._turn_timestamps.append(message.timestamp)

            elif message.type == "llm_latency":
                payload = message.payload or {}
                latency = payload.get("latency_s")
                if latency is not None:
                    self._check_latency_spike(latency)

            elif message.type == "queue_stuck":
                self._check_queue_saturation(message.source)

            elif message.type == "processor_failure":
                self._error_timestamps.append(message.timestamp)
                self._check_error_rate()
                self._post_alert(Alert(
                    alert_type="processor_failure",
                    severity="critical",
                    message=f"Processor failure: {message.source}",
                    source=message.source,
                    metadata=message.payload or {},
                ))

    def _check_latency_spike(self, latency: float) -> None:
        """Detect sustained latency spikes (>2x p95 for N consecutive turns)."""
        if len(self._latency_history) < 10:
            self._latency_history.append(latency)
            return  # Need enough data for p95

        # Compute p95 from existing history BEFORE adding current value
        sorted_vals = sorted(self._latency_history)
        p95_idx = int(len(sorted_vals) * 0.95)
        p95 = sorted_vals[min(p95_idx, len(sorted_vals) - 1)]

        self._latency_history.append(latency)

        threshold = p95 * self._thresholds.latency_spike_multiplier
        if latency > threshold:
            self._consecutive_spikes += 1
        else:
            self._consecutive_spikes = 0

        if self._consecutive_spikes >= self._thresholds.latency_spike_consecutive:
            self._post_alert(Alert(
                alert_type="latency_spike",
                severity="warning",
                message=(
                    f"Latency spike: {latency:.2f}s > {threshold:.2f}s "
                    f"(p95={p95:.2f}s) for {self._consecutive_spikes} consecutive turns"
                ),
                source="pipeline",
                metadata={"latency": latency, "p95": p95, "consecutive": self._consecutive_spikes},
            ))
            self._consecutive_spikes = 0  # Reset after alert

    def _check_error_rate(self) -> None:
        """Detect high error rate (>threshold in sliding window)."""
        now = time.time()
        window = self._thresholds.error_rate_window_s

        # Count errors in window
        recent_errors = sum(
            1 for ts in self._error_timestamps if (now - ts) <= window
        )
        recent_turns = sum(
            1 for ts in self._turn_timestamps if (now - ts) <= window
        )

        if recent_turns == 0:
            return

        error_rate = recent_errors / recent_turns
        if error_rate >= self._thresholds.error_rate_threshold:
            self._post_alert(Alert(
                alert_type="error_rate",
                severity="critical",
                message=(
                    f"Error rate {error_rate:.1%} exceeds threshold "
                    f"{self._thresholds.error_rate_threshold:.1%} "
                    f"({recent_errors}/{recent_turns} in last {window:.0f}s)"
                ),
                source="pipeline",
                metadata={
                    "error_rate": error_rate,
                    "errors": recent_errors,
                    "turns": recent_turns,
                },
            ))

    def _check_queue_saturation(self, queue_name: str) -> None:
        """Detect sustained queue saturation (>threshold for >duration)."""
        now = time.monotonic()
        if queue_name not in self._saturation_start:
            self._saturation_start[queue_name] = now
            return

        duration = now - self._saturation_start[queue_name]
        if duration >= self._thresholds.queue_saturation_duration_s:
            self._post_alert(Alert(
                alert_type="queue_saturation",
                severity="warning",
                message=(
                    f"Queue {queue_name} saturated for {duration:.0f}s "
                    f"(threshold: {self._thresholds.queue_saturation_duration_s:.0f}s)"
                ),
                source=queue_name,
                metadata={"duration_s": duration},
            ))
            # Reset so we don't fire every check
            self._saturation_start[queue_name] = now

    def _post_alert(self, alert: Alert) -> None:
        """Post alert to bus if not in cooldown."""
        cooldown = self._thresholds.alert_cooldown_s
        last_fired = self._last_alert_at.get(alert.alert_type, 0.0)

        if (time.time() - last_fired) < cooldown:
            return  # Cooldown active

        self._last_alert_at[alert.alert_type] = time.time()
        self._alerts.append(alert)
        self._bus.post(
            BusMessage(type="alert", source=alert.source, payload=alert)
        )
        logger.warning("Alert [%s] %s: %s", alert.severity, alert.alert_type, alert.message)

    def snapshot(self) -> list[dict[str, Any]]:
        """Return recent alerts as JSON-serializable list."""
        with self._lock:
            return [
                {
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "message": a.message,
                    "source": a.source,
                    "timestamp": a.timestamp,
                }
                for a in self._alerts[-20:]  # Last 20 alerts
            ]

    def reset(self) -> None:
        """Clear all tracking state."""
        with self._lock:
            self._latency_history.clear()
            self._consecutive_spikes = 0
            self._error_timestamps.clear()
            self._turn_timestamps.clear()
            self._saturation_start.clear()
            self._last_alert_at.clear()
            self._alerts.clear()


class AlertDispatcher:
    """Subscribes to alert bus messages and dispatches to external channels.

    Supports webhook (HTTP POST) and log-only modes.
    """

    def __init__(self, bus: Bus, webhook_url: str | None = None) -> None:
        self._bus = bus
        self._webhook_url = webhook_url
        bus.subscribe("alert", self._on_alert)

    def _on_alert(self, message: BusMessage) -> None:
        """Dispatch alert to configured channels."""
        alert: Alert = message.payload
        if not isinstance(alert, Alert):
            return

        # Always log
        logger.warning(
            "ALERT [%s] %s: %s (source=%s)",
            alert.severity,
            alert.alert_type,
            alert.message,
            alert.source,
        )

        # Webhook dispatch (fire-and-forget in thread pool)
        if self._webhook_url:
            self._send_webhook(alert)

    def _send_webhook(self, alert: Alert) -> None:
        """Send alert to webhook URL via HTTP POST."""
        import concurrent.futures

        def _post():
            try:
                import json
                import urllib.request

                data = json.dumps({
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "message": alert.message,
                    "source": alert.source,
                    "timestamp": alert.timestamp,
                    "metadata": alert.metadata,
                }).encode("utf-8")

                req = urllib.request.Request(
                    self._webhook_url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                logger.error(
                    "Webhook dispatch failed for alert %s", alert.alert_type, exc_info=True
                )

        # Use thread to avoid blocking bus dispatch
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(_post)
        executor.shutdown(wait=False)
