"""Pipeline builder and runtime container."""

import logging
from typing import Any

from .bus import Bus
from .event import PipelineEvent
from .processor import FlowReturn, Processor
from .queue import ThreadedQueue

logger = logging.getLogger(__name__)


class Pipeline:
    """Owns all processors, queues, and the bus. Manages lifecycle."""

    def __init__(
        self,
        processors: list[Processor],
        queues: list[ThreadedQueue],
        bus: Bus,
    ) -> None:
        self._processors = processors
        self._queues = queues
        self._bus = bus
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def bus(self) -> Bus:
        return self._bus

    async def start(self) -> None:
        """Start all processors and queues."""
        if self._running:
            return
        for proc in self._processors:
            await proc.start()
        for q in self._queues:
            q.start()
        self._running = True
        logger.info(
            "Pipeline started with %d processors, %d queues",
            len(self._processors),
            len(self._queues),
        )

    async def stop(self) -> None:
        """Stop all queues and processors."""
        if not self._running:
            return
        for q in self._queues:
            q.stop()
        for proc in reversed(self._processors):
            await proc.stop()
        self._running = False
        logger.info("Pipeline stopped")

    def push(self, item: Any) -> FlowReturn:
        """Push an item into the first queue (pipeline entry point)."""
        if not self._queues:
            return FlowReturn.ERROR
        return self._queues[0].push(item)

    def get_processor(self, name: str) -> Processor | None:
        """Look up a processor by name."""
        for proc in self._processors:
            if proc.name == name:
                return proc
        return None

    def send_event(self, event: PipelineEvent) -> None:
        """Propagate an event through all processors (downstream order)."""
        for proc in self._processors:
            consumed = proc.handle_event(event)
            if consumed:
                break

    def send_event_reverse(self, event: PipelineEvent) -> None:
        """Propagate an event in reverse processor order (upstream)."""
        for proc in reversed(self._processors):
            consumed = proc.handle_event(event)
            if consumed:
                break

    def push_at(self, processor_name: str, item: Any) -> FlowReturn:
        """Push an item into the queue feeding the named processor."""
        for i, proc in enumerate(self._processors):
            if proc.name == processor_name:
                return self._queues[i].push(item)
        raise ValueError(f"Processor {processor_name!r} not found")

    def flush_all(self) -> None:
        """Flush all ThreadedQueues (drain without processing)."""
        for q in self._queues:
            q.flush()


class PipelineBuilder:
    """Builds a pipeline from a list of processors, inserting ThreadedQueues at boundaries."""

    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._processors: list[Processor] = []

    def add(self, processor: Processor) -> "PipelineBuilder":
        """Add a processor to the pipeline."""
        self._processors.append(processor)
        return self

    def build(self) -> Pipeline:
        """Build the pipeline, inserting ThreadedQueues between processors."""
        if not self._processors:
            return Pipeline(processors=[], queues=[], bus=self._bus)

        queues: list[ThreadedQueue] = []

        # Create a ThreadedQueue before each processor
        for i, proc in enumerate(self._processors):
            q = ThreadedQueue(name=f"q_{i}_{proc.name}", maxsize=10)
            q.link(proc)
            queues.append(q)

        # Chain queues so each processor's output flows to the next queue
        for i in range(len(queues) - 1):
            queues[i].chain(queues[i + 1])
            # Also set _next_queue on processors that need direct access
            proc = self._processors[i]
            if hasattr(proc, '_next_queue'):
                proc._next_queue = queues[i + 1]

        return Pipeline(
            processors=list(self._processors),
            queues=queues,
            bus=self._bus,
        )
