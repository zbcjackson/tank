"""FanOutQueue — pushes processor outputs to N branch queues simultaneously."""

from __future__ import annotations

import asyncio
import logging
import queue

from .processor import FlowReturn
from .queue import ThreadedQueue

logger = logging.getLogger(__name__)


class FanOutQueue(ThreadedQueue):
    """ThreadedQueue that fans out processor outputs to multiple branch queues.

    Instead of forwarding to a single ``_next_queue``, pushes each output
    to every registered branch queue.  Each branch queue runs its own
    consumer thread, so branches execute in parallel.
    """

    def __init__(self, name: str, maxsize: int = 10) -> None:
        super().__init__(name=name, maxsize=maxsize)
        self._fan_out_queues: list[ThreadedQueue] = []

    def add_branch(self, branch_queue: ThreadedQueue) -> None:
        """Register a branch queue to receive copies of processor output."""
        self._fan_out_queues.append(branch_queue)

    async def _async_consumer(self) -> None:
        """Override: fan out processor outputs to all branch queues."""
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                await asyncio.sleep(0)
                continue

            if self._downstream is None:
                continue

            try:
                async for status, output in self._downstream.process(item):
                    if status == FlowReturn.EOS:
                        self._stop_event.set()
                        return
                    if output is not None:
                        for branch_q in self._fan_out_queues:
                            branch_q.push(output)
            except Exception:
                logger.error(
                    "FanOutQueue %s: downstream processor error", self.name, exc_info=True
                )
