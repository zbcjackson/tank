"""Thread-safe message bus for pipeline-wide communication."""

import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BusMessage:
    """Message posted to the bus."""

    type: str
    source: str
    payload: Any = None
    timestamp: float = field(default_factory=time.time)


class Bus:
    """Thread-safe publish/subscribe message bus.

    Processors and observers post messages; subscribers receive them.
    Messages are queued and dispatched via `poll()` from the app thread.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[BusMessage], None]]] = defaultdict(list)
        self._pending: list[BusMessage] = []
        self._lock = threading.Lock()

    def post(self, message: BusMessage) -> None:
        """Post a message to the bus (thread-safe)."""
        with self._lock:
            self._pending.append(message)

    def subscribe(self, msg_type: str, handler: Callable[[BusMessage], None]) -> None:
        """Subscribe to messages of a given type."""
        self._subscribers[msg_type].append(handler)

    def poll(self) -> int:
        """Dispatch all pending messages to subscribers. Returns count dispatched."""
        with self._lock:
            batch = list(self._pending)
            self._pending.clear()

        dispatched = 0
        for message in batch:
            for handler in self._subscribers.get(message.type, []):
                try:
                    handler(message)
                    dispatched += 1
                except Exception:
                    logger.error(
                        "Bus handler error for %s from %s",
                        message.type,
                        message.source,
                        exc_info=True,
                    )
        return dispatched
