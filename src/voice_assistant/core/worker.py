"""Reusable worker thread utilities."""

from __future__ import annotations

import threading
import time
import queue
from typing import Generic, TypeVar, Optional

from .shutdown import StopSignal

T = TypeVar("T")


class QueueWorker(threading.Thread, Generic[T]):
    """
    Base class for a queue-consuming worker thread.

    This keeps lifecycle + polling logic consistent and reduces duplication across worker threads.
    Subclasses only implement `handle(item)`.
    """

    def __init__(
        self,
        *,
        name: str,
        stop_signal: StopSignal,
        input_queue: "queue.Queue[T]",
        poll_interval_s: float = 0.1,
        daemon: bool = True,
    ):
        super().__init__(name=name, daemon=daemon)
        self._stop_signal = stop_signal
        self._input_queue = input_queue
        self._poll_interval_s = poll_interval_s

    def run(self) -> None:
        while not self._stop_signal.is_set():
            try:
                item = self._input_queue.get(timeout=self._poll_interval_s)
            except queue.Empty:
                continue

            try:
                self.handle(item)
            finally:
                self._input_queue.task_done()

    def handle(self, item: T) -> None:
        raise NotImplementedError

