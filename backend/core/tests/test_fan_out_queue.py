"""Tests for FanOutQueue."""

import asyncio

from tank_backend.pipeline.fan_out_queue import FanOutQueue
from tank_backend.pipeline.processor import FlowReturn, Processor
from tank_backend.pipeline.queue import ThreadedQueue


class CollectorProcessor(Processor):
    """Test processor that collects items."""

    def __init__(self, name: str):
        super().__init__(name)
        self.items: list = []

    async def process(self, item):
        self.items.append(item)
        yield FlowReturn.OK, item


class TestFanOutQueue:
    async def test_fan_out_to_multiple_branches(self):
        """FanOutQueue should push processor output to all branch queues."""
        # Create a processor that outputs items
        source_proc = CollectorProcessor("source")
        fan_q = FanOutQueue(name="fan_out", maxsize=10)
        fan_q.link(source_proc)

        # Create two branch queues with collectors
        branch1_proc = CollectorProcessor("branch1")
        branch1_q = ThreadedQueue(name="branch1_q", maxsize=10)
        branch1_q.link(branch1_proc)

        branch2_proc = CollectorProcessor("branch2")
        branch2_q = ThreadedQueue(name="branch2_q", maxsize=10)
        branch2_q.link(branch2_proc)

        fan_q.add_branch(branch1_q)
        fan_q.add_branch(branch2_q)

        # Start queues
        fan_q.start()
        branch1_q.start()
        branch2_q.start()

        # Push items
        fan_q.push("item1")
        fan_q.push("item2")

        # Wait for processing
        await asyncio.sleep(0.2)

        # Stop queues
        fan_q.stop()
        branch1_q.stop()
        branch2_q.stop()

        # Both branches should receive all items
        assert source_proc.items == ["item1", "item2"]
        assert branch1_proc.items == ["item1", "item2"]
        assert branch2_proc.items == ["item1", "item2"]

    async def test_fan_out_with_three_branches(self):
        """FanOutQueue should work with more than 2 branches."""
        source_proc = CollectorProcessor("source")
        fan_q = FanOutQueue(name="fan_out", maxsize=10)
        fan_q.link(source_proc)

        branches = []
        for i in range(3):
            proc = CollectorProcessor(f"branch{i}")
            q = ThreadedQueue(name=f"branch{i}_q", maxsize=10)
            q.link(proc)
            fan_q.add_branch(q)
            branches.append((q, proc))

        fan_q.start()
        for q, _ in branches:
            q.start()

        fan_q.push("test")
        await asyncio.sleep(0.2)

        fan_q.stop()
        for q, _ in branches:
            q.stop()

        for _, proc in branches:
            assert proc.items == ["test"]

    async def test_fan_out_empty_branches(self):
        """FanOutQueue with no branches should not crash."""
        source_proc = CollectorProcessor("source")
        fan_q = FanOutQueue(name="fan_out", maxsize=10)
        fan_q.link(source_proc)

        fan_q.start()
        result = fan_q.push("item")
        await asyncio.sleep(0.1)
        fan_q.stop()

        assert result == FlowReturn.OK
        assert source_proc.items == ["item"]
