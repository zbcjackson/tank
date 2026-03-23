"""Bounded queue that creates a thread boundary between pipeline stages."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any

from .health import QueueHealth
from .processor import FlowReturn, Processor

logger = logging.getLogger(__name__)


class ThreadedQueue:
    """Bounded queue that spawns a consumer thread = thread boundary.

    Connects two processors across a thread boundary. The producer pushes
    items via `push()`, and the consumer thread drains them into the
    downstream processor.
    """

    def __init__(self, name: str, maxsize: int = 10) -> None:
        self.name = name
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=maxsize)
        self._downstream: Processor | None = None
        self._next_queue: ThreadedQueue | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._blocked = threading.Event()  # set = blocked (for dynamic swap)
        self._loop: Any = None  # asyncio event loop for the consumer thread
        self._last_consumed_at: float | None = None  # monotonic timestamp
        self._consecutive_failures: int = 0

    def link(self, downstream: Processor) -> None:
        """Set the downstream processor that consumes from this queue."""
        self._downstream = downstream

    def chain(self, next_queue: ThreadedQueue) -> None:
        """Set the next queue to forward processor outputs to."""
        self._next_queue = next_queue

    def push(self, item: Any) -> FlowReturn:
        """Push an item into the queue. Blocks if full (backpressure)."""
        if self._stop_event.is_set():
            return FlowReturn.EOS
        if self._blocked.is_set():
            return FlowReturn.FLUSHING
        try:
            self._queue.put(item, timeout=1.0)
            return FlowReturn.OK
        except queue.Full:
            logger.warning("Queue %s full — backpressure", self.name)
            return FlowReturn.ERROR

    def start(self) -> None:
        """Start the consumer thread."""
        if self._downstream is None:
            raise RuntimeError(f"Queue {self.name} has no downstream processor linked")
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._consumer_loop, name=f"Queue-{self.name}", daemon=True
        )
        self._thread.start()
        logger.debug("Queue %s started", self.name)

    def stop(self) -> None:
        """Stop the consumer thread and drain remaining items."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.debug("Queue %s stopped", self.name)

    def flush(self) -> None:
        """Drain all pending items without processing (for interrupt)."""
        drained = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                drained += 1
            except queue.Empty:
                break
        if drained:
            logger.debug("Queue %s flushed %d items", self.name, drained)

    @property
    def qsize(self) -> int:
        """Current number of items in the queue."""
        return self._queue.qsize()

    def health(self, stuck_threshold_s: float = 10.0) -> QueueHealth:
        """Return a snapshot of this queue's health state."""
        now = time.monotonic()
        size = self._queue.qsize()
        is_stuck = (
            size > 0
            and self._last_consumed_at is not None
            and (now - self._last_consumed_at) > stuck_threshold_s
        )
        return QueueHealth(
            name=self.name,
            size=size,
            maxsize=self._queue.maxsize,
            last_consumed_at=self._last_consumed_at,
            is_stuck=is_stuck,
            consumer_alive=self._thread is not None and self._thread.is_alive(),
        )

    def block(self) -> None:
        """Block upstream pushes (for dynamic processor swap)."""
        self._blocked.set()

    def unblock(self) -> None:
        """Unblock upstream pushes."""
        self._blocked.clear()

    def _consumer_loop(self) -> None:
        """Consumer thread: drain queue into downstream processor."""
        import asyncio

        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            loop.run_until_complete(self._async_consumer())
        finally:
            loop.close()
            self._loop = None

    async def _async_consumer(self) -> None:
        """Async consumer that processes items from the queue."""
        import asyncio

        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                await asyncio.sleep(0)
                continue

            self._last_consumed_at = time.monotonic()

            if self._downstream is None:
                continue

            try:
                async for status, output in self._downstream.process(item):
                    if status == FlowReturn.EOS:
                        self._stop_event.set()
                        return
                    if output is not None and self._next_queue is not None:
                        self._next_queue.push(output)
                self._consecutive_failures = 0
            except Exception:
                self._consecutive_failures += 1
                logger.error(
                    "Queue %s: downstream processor error (consecutive=%d)",
                    self.name,
                    self._consecutive_failures,
                    exc_info=True,
                )
