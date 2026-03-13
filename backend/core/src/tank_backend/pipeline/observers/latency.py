"""Latency observer — tracks time between pipeline stages."""

import logging

from ..bus import Bus, BusMessage

logger = logging.getLogger(__name__)


class LatencyObserver:
    """Measures latency between start/end events posted to the bus.

    Subscribes to "stage_start" and "stage_end" messages. When a matching
    pair is seen (same source), logs the elapsed time.
    """

    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._starts: dict[str, float] = {}
        self._latencies: list[tuple[str, float]] = []
        bus.subscribe("stage_start", self.on_message)
        bus.subscribe("stage_end", self.on_message)

    def on_message(self, message: BusMessage) -> None:
        if message.type == "stage_start":
            self._starts[message.source] = message.timestamp
        elif message.type == "stage_end":
            start_time = self._starts.pop(message.source, None)
            if start_time is not None:
                elapsed = message.timestamp - start_time
                self._latencies.append((message.source, elapsed))
                logger.debug("Latency %s: %.3fs", message.source, elapsed)

    @property
    def latencies(self) -> list[tuple[str, float]]:
        """Return recorded (source, elapsed_seconds) pairs."""
        return list(self._latencies)

    def reset(self) -> None:
        """Clear recorded latencies."""
        self._starts.clear()
        self._latencies.clear()
