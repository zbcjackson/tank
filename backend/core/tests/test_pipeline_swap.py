"""Tests for dynamic processor swap via Pipeline.swap_processor()."""

import asyncio
import time

import pytest

from tank_backend.pipeline.builder import PipelineBuilder
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processor import FlowReturn, Processor


class CollectorProcessor(Processor):
    """Test processor that collects items."""

    def __init__(self, name: str, prefix: str = ""):
        super().__init__(name)
        self.collected: list = []
        self.prefix = prefix

    async def process(self, item):
        result = f"{self.prefix}{item}"
        self.collected.append(result)
        yield FlowReturn.OK, result


class SlowProcessor(Processor):
    """Processor that takes some time."""

    def __init__(self, name: str):
        super().__init__(name)
        self.collected: list = []

    async def process(self, item):
        self.collected.append(item)
        await asyncio.sleep(0.05)
        yield FlowReturn.OK, f"slow_{item}"


class TestSwapProcessor:
    @pytest.mark.asyncio
    async def test_swap_replaces_processor(self):
        """swap_processor should replace old processor with new one."""
        bus = Bus()
        old_proc = CollectorProcessor("target", prefix="old_")
        sink = CollectorProcessor("sink")

        builder = PipelineBuilder(bus)
        builder.add(old_proc)
        builder.add(sink)
        pipeline = builder.build()
        await pipeline.start()

        try:
            # Process with old
            pipeline.push("item1")
            time.sleep(0.3)
            assert "old_item1" in old_proc.collected

            # Swap
            new_proc = CollectorProcessor("target", prefix="new_")
            await pipeline.swap_processor("target", new_proc)

            # Process with new
            pipeline.push("item2")
            time.sleep(0.3)
            assert "new_item2" in new_proc.collected
            assert "new_item2" not in old_proc.collected
        finally:
            await pipeline.stop()

    @pytest.mark.asyncio
    async def test_swap_nonexistent_raises(self):
        """swap_processor should raise ValueError for unknown processor."""
        bus = Bus()
        proc = CollectorProcessor("a")
        builder = PipelineBuilder(bus)
        builder.add(proc)
        pipeline = builder.build()
        await pipeline.start()

        try:
            with pytest.raises(ValueError, match="not found"):
                await pipeline.swap_processor("nonexistent", CollectorProcessor("b"))
        finally:
            await pipeline.stop()

    @pytest.mark.asyncio
    async def test_swap_blocks_upstream(self):
        """Upstream pushes should return FLUSHING during swap."""
        bus = Bus()
        proc_a = CollectorProcessor("a")
        proc_b = CollectorProcessor("b")

        builder = PipelineBuilder(bus)
        builder.add(proc_a)
        builder.add(proc_b)
        pipeline = builder.build()
        await pipeline.start()

        try:
            # Block the first queue to test push behavior
            queue_a = pipeline._queues[0]

            # Manually block to test the push behavior
            queue_a.block()
            result = queue_a.push("blocked_item")
            assert result == FlowReturn.FLUSHING
            queue_a.unblock()
        finally:
            await pipeline.stop()


class TestRestartProcessor:
    @pytest.mark.asyncio
    async def test_restart_recovers(self):
        """restart_processor should restore processing after stop."""
        bus = Bus()
        proc = CollectorProcessor("target", prefix="r_")
        sink = CollectorProcessor("sink")

        builder = PipelineBuilder(bus)
        builder.add(proc)
        builder.add(sink)
        pipeline = builder.build()
        await pipeline.start()

        try:
            # Process before restart
            pipeline.push("before")
            time.sleep(0.3)
            assert "r_before" in proc.collected

            # Restart
            await pipeline.restart_processor("target")

            # Process after restart
            pipeline.push("after")
            time.sleep(0.3)
            assert "r_after" in proc.collected
        finally:
            await pipeline.stop()

    @pytest.mark.asyncio
    async def test_restart_unknown_processor(self):
        """restart_processor should not raise for unknown processor."""
        bus = Bus()
        proc = CollectorProcessor("a")
        builder = PipelineBuilder(bus)
        builder.add(proc)
        pipeline = builder.build()
        await pipeline.start()

        try:
            # Should not raise, just log warning
            await pipeline.restart_processor("nonexistent")
        finally:
            await pipeline.stop()


class TestHealthSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_reflects_running_state(self):
        """health_snapshot should report running state correctly."""
        bus = Bus()
        proc = CollectorProcessor("proc")
        builder = PipelineBuilder(bus)
        builder.add(proc)
        pipeline = builder.build()

        snapshot_before = pipeline.health_snapshot()
        assert snapshot_before.running is False

        await pipeline.start()
        time.sleep(0.1)

        try:
            snapshot_running = pipeline.health_snapshot()
            assert snapshot_running.running is True
            assert snapshot_running.is_healthy is True
            assert len(snapshot_running.queues) == 1
            assert snapshot_running.queues[0].consumer_alive is True
        finally:
            await pipeline.stop()

    @pytest.mark.asyncio
    async def test_snapshot_after_stop(self):
        """health_snapshot should report not running after stop."""
        bus = Bus()
        proc = CollectorProcessor("proc")
        builder = PipelineBuilder(bus)
        builder.add(proc)
        pipeline = builder.build()

        await pipeline.start()
        await pipeline.stop()

        snapshot = pipeline.health_snapshot()
        assert snapshot.running is False
