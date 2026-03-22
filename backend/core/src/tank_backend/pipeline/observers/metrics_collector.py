"""MetricsCollector — aggregates pipeline metrics from Bus messages."""

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from ..bus import Bus, BusMessage

logger = logging.getLogger(__name__)


@dataclass
class LatencyStats:
    """Aggregated latency statistics for a metric."""

    history: list[float] = field(default_factory=list)

    @property
    def last(self) -> float | None:
        return self.history[-1] if self.history else None

    @property
    def avg(self) -> float | None:
        return sum(self.history) / len(self.history) if self.history else None

    @property
    def min(self) -> float | None:
        return min(self.history) if self.history else None

    @property
    def max(self) -> float | None:
        return max(self.history) if self.history else None

    def record(self, value: float) -> None:
        self.history.append(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "last": self.last,
            "avg": round(self.avg, 4) if self.avg is not None else None,
            "min": round(self.min, 4) if self.min is not None else None,
            "max": round(self.max, 4) if self.max is not None else None,
            "history": [round(v, 4) for v in self.history],
        }


class MetricsCollector:
    """Collects and aggregates pipeline metrics from Bus messages.

    Subscribes to all bus messages and correlates timestamps to compute:
    - ASR latency (from ``asr_result`` payload)
    - LLM latency (from ``llm_latency`` payload)
    - TTS latency (from ``tts_finished`` payload)
    - End-to-end response latency (``asr_result`` → ``playback_started``)

    Thread-safe: Bus dispatches from the poll thread.
    """

    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._lock = threading.Lock()

        # Per-metric stats
        self._asr = LatencyStats()
        self._llm = LatencyStats()
        self._tts = LatencyStats()
        self._end_to_end = LatencyStats()

        # Counters
        self._turns = 0
        self._echo_discards = 0
        self._interrupts = 0

        # Correlation: timestamp of last asr_result for e2e computation
        self._last_asr_result_ts: float | None = None

        # Langfuse trace IDs collected per turn
        self._trace_ids: list[str] = []

        # Subscribe to relevant message types
        bus.subscribe("asr_result", self._on_message)
        bus.subscribe("llm_latency", self._on_message)
        bus.subscribe("tts_finished", self._on_message)
        bus.subscribe("playback_started", self._on_message)
        bus.subscribe("echo_discarded", self._on_message)
        bus.subscribe("speech_start", self._on_message)
        bus.subscribe("trace_id", self._on_message)

    def _on_message(self, message: BusMessage) -> None:
        with self._lock:
            if message.type == "asr_result":
                self._turns += 1
                payload = message.payload or {}
                latency = payload.get("latency_s")
                if latency is not None:
                    self._asr.record(latency)
                # Record timestamp for e2e correlation
                self._last_asr_result_ts = message.timestamp

            elif message.type == "llm_latency":
                payload = message.payload or {}
                latency = payload.get("latency_s")
                if latency is not None:
                    self._llm.record(latency)

            elif message.type == "tts_finished":
                payload = message.payload or {}
                latency = payload.get("latency_s")
                if latency is not None:
                    self._tts.record(latency)

            elif message.type == "playback_started":
                # Compute end-to-end: asr_result timestamp → playback_started timestamp
                if self._last_asr_result_ts is not None:
                    e2e = message.timestamp - self._last_asr_result_ts
                    self._end_to_end.record(e2e)
                    logger.debug("E2E latency: %.3fs", e2e)
                    self._last_asr_result_ts = None

            elif message.type == "echo_discarded":
                self._echo_discards += 1

            elif message.type == "speech_start":
                self._interrupts += 1

            elif message.type == "trace_id":
                payload = message.payload or {}
                trace_id = payload.get("trace_id")
                if trace_id:
                    self._trace_ids.append(trace_id)

    def snapshot(self) -> dict[str, Any]:
        """Return current metrics as a JSON-serializable dict."""
        with self._lock:
            return {
                "turns": self._turns,
                "latencies": {
                    "end_to_end": self._end_to_end.to_dict(),
                    "asr": self._asr.to_dict(),
                    "llm": self._llm.to_dict(),
                    "tts": self._tts.to_dict(),
                },
                "echo_discards": self._echo_discards,
                "interrupts": self._interrupts,
                "langfuse_trace_ids": list(self._trace_ids),
            }

    def reset(self) -> None:
        """Clear all collected metrics."""
        with self._lock:
            self._asr = LatencyStats()
            self._llm = LatencyStats()
            self._tts = LatencyStats()
            self._end_to_end = LatencyStats()
            self._turns = 0
            self._echo_discards = 0
            self._interrupts = 0
            self._last_asr_result_ts = None
            self._trace_ids.clear()
