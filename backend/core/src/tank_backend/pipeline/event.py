"""Pipeline events for inter-stage communication."""

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventDirection(Enum):
    """Direction of event propagation."""

    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"


@dataclass(frozen=True)
class PipelineEvent:
    """Event that propagates through the pipeline."""

    type: str
    direction: EventDirection = EventDirection.DOWNSTREAM
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DrainSentinel:
    """Data-path sentinel that proves a pipeline drained (s2s SESSION_END).

    Unlike :class:`PipelineEvent` — which propagates synchronously and says
    nothing about queued data — this rides the data path: it is pushed into a
    queue and forwarded by each processor it passes. The terminal processor
    calls :meth:`arrive` when it sees the sentinel, so whoever awaits
    :meth:`wait` knows every item queued ahead of it has been consumed —
    including an in-flight batch still producing downstream output.
    """

    _arrived: threading.Event = field(default_factory=threading.Event)

    def arrive(self) -> None:
        """Called by the terminal processor when the sentinel crosses the chain."""
        self._arrived.set()

    def wait(self, timeout: float) -> bool:
        """Block until the sentinel arrives; False if ``timeout`` elapses first."""
        return self._arrived.wait(timeout)
