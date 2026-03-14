"""Interrupt latency observer — tracks time from speech detection to interrupt acknowledgment."""

import logging

from ..bus import Bus, BusMessage

logger = logging.getLogger(__name__)


class InterruptLatencyObserver:
    """Measures latency between speech_start and interrupt_ack events.

    Subscribes to "speech_start" and "interrupt_ack" messages on the bus.
    Records elapsed time between speech detection and processor acknowledgments.
    """

    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._speech_start_time: float | None = None
        self._latencies: list[tuple[str, float]] = []
        bus.subscribe("speech_start", self._on_message)
        bus.subscribe("interrupt_ack", self._on_message)

    def _on_message(self, message: BusMessage) -> None:
        if message.type == "speech_start":
            self._speech_start_time = message.timestamp
        elif message.type == "interrupt_ack" and self._speech_start_time is not None:
                elapsed = message.timestamp - self._speech_start_time
                self._latencies.append((message.source, elapsed))
                logger.debug(
                    "Interrupt latency %s: %.3fs", message.source, elapsed
                )
                self._speech_start_time = None

    @property
    def latencies(self) -> list[tuple[str, float]]:
        """Return recorded (source, elapsed_seconds) pairs."""
        return list(self._latencies)

    def reset(self) -> None:
        """Clear recorded latencies."""
        self._speech_start_time = None
        self._latencies.clear()
