"""Pipeline builder and runtime container."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .bus import Bus
from .event import PipelineEvent
from .fan_out_queue import FanOutQueue
from .health import PipelineHealth, ProcessorHealth
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

    def health_snapshot(self, stuck_threshold_s: float = 10.0) -> PipelineHealth:
        """Collect health from all processors and queues."""
        queue_health = [q.health(stuck_threshold_s) for q in self._queues]
        processor_health = []
        for i, proc in enumerate(self._processors):
            q = self._queues[i] if i < len(self._queues) else None
            processor_health.append(
                ProcessorHealth(
                    name=proc.name,
                    is_running=q.health().consumer_alive if q else True,
                    consecutive_failures=q._consecutive_failures if q else 0,
                    last_error=None,
                )
            )
        is_healthy = (
            self._running
            and all(qh.consumer_alive for qh in queue_health)
            and not any(qh.is_stuck for qh in queue_health)
        )
        return PipelineHealth(
            running=self._running,
            processors=processor_health,
            queues=queue_health,
            is_healthy=is_healthy,
        )

    async def swap_processor(self, name: str, new_processor: Processor) -> None:
        """Hot-swap a processor without restarting the pipeline.

        Sequence: block upstream → flush target queue → stop old processor →
        replace → start new → unblock upstream.
        """
        idx = next(
            (i for i, p in enumerate(self._processors) if p.name == name), None
        )
        if idx is None:
            raise ValueError(f"Processor {name!r} not found")

        old_proc = self._processors[idx]
        feeding_queue = self._queues[idx]

        # 1. Block the queue that feeds into the target queue
        upstream_queue: ThreadedQueue | None = None
        for q in self._queues:
            if q._next_queue is feeding_queue:
                upstream_queue = q
                break
        if upstream_queue is not None:
            upstream_queue.block()

        # 2. Drain the feeding queue
        feeding_queue.flush()

        # 3. Stop old processor
        feeding_queue.stop()
        await old_proc.stop()

        # 4. Replace
        feeding_queue.link(new_processor)
        self._processors[idx] = new_processor

        # 5. Start new
        await new_processor.start()
        feeding_queue.start()

        # 6. Unblock upstream
        if upstream_queue is not None:
            upstream_queue.unblock()

        logger.info(
            "Swapped processor %r → %r",
            old_proc.name,
            new_processor.name,
        )

    async def restart_processor(self, name: str) -> None:
        """Restart a processor's queue consumer thread (for auto-recovery)."""
        idx = next(
            (i for i, p in enumerate(self._processors) if p.name == name), None
        )
        if idx is None:
            logger.warning("Cannot restart unknown processor %r", name)
            return
        q = self._queues[idx]
        proc = self._processors[idx]
        q.stop()
        await proc.stop()
        await proc.start()
        q.start()
        logger.info("Restarted processor %r", name)


class PipelineBuilder:
    """Builds a pipeline from a list of processors, inserting ThreadedQueues at boundaries.

    Supports fan-out/fan-in regions for parallel processing branches.
    """

    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._steps: list[_BuildStep] = []

    def add(self, processor: Processor) -> PipelineBuilder:
        """Add a processor to the pipeline."""
        self._steps.append(_BuildStep(kind="linear", processors=[processor]))
        return self

    def fan_out(self, *branches: list[Processor]) -> PipelineBuilder:
        """Fan out: previous processor's output goes to all branches in parallel.

        Each argument is a list of processors forming one branch.
        """
        if not branches or len(branches) < 2:
            raise ValueError("fan_out requires at least 2 branches")
        self._steps.append(_BuildStep(kind="fan_out", branches=list(branches)))
        return self

    def fan_in(self, merger: Processor) -> PipelineBuilder:
        """Fan in: collect results from all active branches into merger processor."""
        self._steps.append(_BuildStep(kind="fan_in", processors=[merger]))
        return self

    def build(self) -> Pipeline:
        """Build the pipeline, inserting ThreadedQueues between processors."""
        if not self._steps:
            return Pipeline(processors=[], queues=[], bus=self._bus)

        all_processors: list[Processor] = []
        all_queues: list[ThreadedQueue] = []
        # The queue whose output should chain to the next stage
        tail_queue: ThreadedQueue | None = None
        queue_counter = 0

        for step in self._steps:
            if step.kind == "linear":
                proc = step.processors[0]
                q = ThreadedQueue(name=f"q_{queue_counter}_{proc.name}", maxsize=10)
                q.link(proc)
                queue_counter += 1

                # Chain from previous tail
                if tail_queue is not None:
                    tail_queue.chain(q)
                    # Also set _next_queue on processors that need direct access
                    prev_proc = all_processors[-1] if all_processors else None
                    if prev_proc is not None and hasattr(prev_proc, "_next_queue"):
                        prev_proc._next_queue = q

                all_processors.append(proc)
                all_queues.append(q)
                tail_queue = q

            elif step.kind == "fan_out":
                # Replace the current tail queue with a FanOutQueue
                # The previous processor's output fans out to all branches
                if tail_queue is None:
                    raise ValueError("fan_out must follow at least one add()")

                # Convert the tail queue to a FanOutQueue
                prev_proc = all_processors[-1]
                prev_idx = all_queues.index(tail_queue)
                fan_q = FanOutQueue(name=tail_queue.name + "_fanout", maxsize=10)
                fan_q.link(tail_queue._downstream)  # same downstream processor
                # Rechain: if there was a queue before tail, point it to fan_q
                for q in all_queues:
                    if q._next_queue is tail_queue:
                        q.chain(fan_q)
                all_queues[prev_idx] = fan_q
                tail_queue = fan_q

                # Build each branch as a sub-chain
                branch_tail_queues: list[ThreadedQueue] = []
                for branch_procs in step.branches:
                    branch_prev_q: ThreadedQueue | None = None
                    for bp in branch_procs:
                        bq = ThreadedQueue(
                            name=f"q_{queue_counter}_{bp.name}", maxsize=10
                        )
                        bq.link(bp)
                        queue_counter += 1

                        if branch_prev_q is not None:
                            branch_prev_q.chain(bq)
                        else:
                            # First processor in branch — fan_q pushes to it
                            fan_q.add_branch(bq)

                        all_processors.append(bp)
                        all_queues.append(bq)
                        branch_prev_q = bq

                    if branch_prev_q is not None:
                        branch_tail_queues.append(branch_prev_q)

                # Store branch tails for fan_in to wire up
                self._branch_tail_queues = branch_tail_queues
                tail_queue = None  # No single tail until fan_in

            elif step.kind == "fan_in":
                merger = step.processors[0]
                merger_q = ThreadedQueue(
                    name=f"q_{queue_counter}_{merger.name}", maxsize=10
                )
                merger_q.link(merger)
                queue_counter += 1

                # All branch tails chain into the merger queue
                if hasattr(self, "_branch_tail_queues"):
                    for btq in self._branch_tail_queues:
                        btq.chain(merger_q)
                    del self._branch_tail_queues

                all_processors.append(merger)
                all_queues.append(merger_q)
                tail_queue = merger_q

        return Pipeline(
            processors=all_processors,
            queues=all_queues,
            bus=self._bus,
        )


@dataclass
class _BuildStep:
    """Internal representation of a builder step."""

    kind: str  # "linear", "fan_out", "fan_in"
    processors: list[Processor] = field(default_factory=list)
    branches: list[list[Processor]] = field(default_factory=list)
