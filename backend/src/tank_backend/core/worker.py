"""Reusable worker thread utilities."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import queue
from typing import Any, Generic, TypeVar, Optional

from .shutdown import StopSignal

T = TypeVar("T")

logger = logging.getLogger(__name__)


class QueueWorker(threading.Thread, Generic[T]):
    """
    Base class for a queue-consuming worker thread.

    This keeps lifecycle + polling logic consistent and reduces duplication across worker threads.
    Subclasses only implement `handle(item)`.

    For subclasses that need an asyncio event loop, override `_setup_event_loop()` to return a loop.
    The base class will manage creation, setting, and cleanup of the loop.
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
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._current_task: Optional[asyncio.Task] = None

    def run(self) -> None:
        """Run the worker thread with optional event loop setup."""
        self._loop = self._setup_event_loop()
        if self._loop is not None:
            asyncio.set_event_loop(self._loop)
        try:
            while not self._stop_signal.is_set():
                try:
                    item = self._input_queue.get(timeout=self._poll_interval_s)
                except queue.Empty:
                    continue

                try:
                    self.handle(item)
                finally:
                    self._input_queue.task_done()
        finally:
            self._teardown_event_loop()

    def _setup_event_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Override in subclasses that need an event loop.

        Return an event loop instance, or None if no loop is needed.
        Default implementation returns None (no loop).
        """
        return None

    def _teardown_event_loop(self) -> None:
        """Cleanup event loop. Override if custom cleanup is needed."""
        if self._loop is not None:
            self._loop.close()
            self._loop = None

    def _run_async(self, coro) -> Any:
        """Run coroutine as a cancellable task in the worker's event loop."""
        assert self._loop is not None, "Event loop not initialized"
        self._current_task = self._loop.create_task(coro)
        try:
            return self._loop.run_until_complete(self._current_task)
        except asyncio.CancelledError:
            logger.debug(f"{self.name}: task cancelled")
            return None
        finally:
            self._current_task = None

    def cancel(self) -> None:
        """Cancel the currently running async task from another thread."""
        task = self._current_task
        if task and self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(task.cancel)

    def handle(self, item: T) -> None:
        raise NotImplementedError

