import threading
from typing import Protocol


class StopSignal(Protocol):
    """Protocol for shutdown signals used by worker threads."""

    def is_set(self) -> bool: ...


class GracefulShutdown:
    def __init__(self):
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def is_set(self) -> bool:
        return self.stop_event.is_set()
