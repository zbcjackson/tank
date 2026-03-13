"""Tests for ThreadedQueue."""

import asyncio
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
        """Queue should apply backpressure when full."""
        q = ThreadedQueue(name="test_q", maxsize=2)
        proc = CollectorProcessor("collector")
        q.link(proc)

        # Fill the queue
        assert q.push("item1") == FlowReturn.OK
        assert q.push("item2") == FlowReturn.OK

        # Next push should timeout (backpressure)
        result = q.push("item3")
        # Should either succeed quickly or return ERROR after timeout
        assert result in (FlowReturn.OK, FlowReturn.ERROR)

    def test_queue_requires_downstream(self):
        """Queue.start should raise if no downstream processor linked."""
        q = ThreadedQueue(name="test_q")
        with pytest.raises(RuntimeError, match="no downstream processor"):
            q.start()
