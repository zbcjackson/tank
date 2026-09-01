"""Tests for ThreadedQueue."""

import asyncio
import threading
import time

import pytest

from tank_backend.pipeline.processor import FlowReturn, Processor
from tank_backend.pipeline.queue import ThreadedQueue


class CollectorProcessor(Processor):
    """Test processor that collects items."""

    def __init__(self, name: str):
        super().__init__(name)
        self.collected = []

    async def process(self, item):
        self.collected.append(item)
        await asyncio.sleep(0.01)  # Simulate work
        yield FlowReturn.OK, f"processed_{item}"


class GatedProcessor(Processor):
    """Test processor that blocks on a gate before collecting."""

    def __init__(self, name: str, gate: threading.Event):
        super().__init__(name)
        self.gate = gate
        self.collected = []

    async def process(self, item):
        await asyncio.get_running_loop().run_in_executor(
            None, self.gate.wait,
        )
        self.collected.append(item)
        yield FlowReturn.OK, None


class TestThreadedQueue:
    def test_queue_init(self):
        """ThreadedQueue should initialize with name and maxsize."""
        q = ThreadedQueue(name="test_q", maxsize=5)
        assert q.name == "test_q"

    def test_queue_link(self):
        """ThreadedQueue.link should set downstream processor."""
        q = ThreadedQueue(name="test_q")
        proc = CollectorProcessor("collector")
        q.link(proc)
        assert q._downstream is proc

    def test_queue_push_before_start(self):
        """Queue.push should accept items before start."""
        q = ThreadedQueue(name="test_q")
        proc = CollectorProcessor("collector")
        q.link(proc)
        result = q.push("item1")
        assert result == FlowReturn.OK

    def test_queue_start_stop(self):
        """Queue should start and stop consumer thread."""
        q = ThreadedQueue(name="test_q")
        proc = CollectorProcessor("collector")
        q.link(proc)

        q.start()
        time.sleep(0.1)  # Let thread start
        q.stop()

    def test_queue_processes_items(self):
        """Queue should drain items into downstream processor."""
        q = ThreadedQueue(name="test_q")
        proc = CollectorProcessor("collector")
        q.link(proc)

        q.push("item1")
        q.push("item2")
        q.push("item3")

        q.start()
        time.sleep(0.2)  # Let items process
        q.stop()

        assert len(proc.collected) == 3
        assert "item1" in proc.collected
        assert "item2" in proc.collected
        assert "item3" in proc.collected

    def test_queue_flush(self):
        """Queue.flush should drain pending items without processing."""
        q = ThreadedQueue(name="test_q")
        proc = CollectorProcessor("collector")
        q.link(proc)

        q.push("item1")
        q.push("item2")
        q.push("item3")

        q.flush()

        # Items should be drained, not processed
        q.start()
        time.sleep(0.1)
        q.stop()

        assert len(proc.collected) == 0

    def test_queue_backpressure(self):
        """Full queue: push blocks (no silent drop); stop() releases it."""
        q = ThreadedQueue(name="test_q", maxsize=2)
        q.link(CollectorProcessor("collector"))

        # Fill the queue
        assert q.push("item1") == FlowReturn.OK
        assert q.push("item2") == FlowReturn.OK

        # No consumer running: the next push must block, not drop
        result: list[FlowReturn] = []
        t = threading.Thread(target=lambda: result.append(q.push("item3")))
        t.start()
        time.sleep(0.05)
        assert t.is_alive()

        q.stop()  # stop_event releases the blocked push
        t.join(timeout=2)
        assert result == [FlowReturn.EOS]

    def test_push_does_not_drop_when_downstream_stalls(self):
        """Items pushed during a downstream stall are all delivered."""
        gate = threading.Event()
        proc = GatedProcessor("gated", gate)
        q = ThreadedQueue(name="test_q", maxsize=2)
        q.link(proc)
        q.start()

        try:
            assert q.push("a") == FlowReturn.OK
            # Let the consumer pick up "a" and block inside the gate
            time.sleep(0.2)
            assert q.push("b") == FlowReturn.OK
            assert q.push("c") == FlowReturn.OK

            # Queue full + stalled downstream: push waits instead of dropping
            # (stall > the old 1s give-up timeout to pin the new contract)
            result: list[FlowReturn] = []
            t = threading.Thread(target=lambda: result.append(q.push("d")))
            t.start()
            time.sleep(1.3)
            assert t.is_alive()

            gate.set()
            t.join(timeout=2)
            assert result == [FlowReturn.OK]

            deadline = time.time() + 2
            while len(proc.collected) < 4 and time.time() < deadline:
                time.sleep(0.01)
            assert proc.collected == ["a", "b", "c", "d"]
        finally:
            gate.set()
            q.stop()

    def test_queue_requires_downstream(self):
        """Queue.start should raise if no downstream processor linked."""
        q = ThreadedQueue(name="test_q")
        with pytest.raises(RuntimeError, match="no downstream processor"):
            q.start()
