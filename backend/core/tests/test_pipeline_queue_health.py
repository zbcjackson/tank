"""Tests for ThreadedQueue health instrumentation."""

import asyncio
import time

from tank_backend.pipeline.health import QueueHealth
from tank_backend.pipeline.processor import FlowReturn, Processor
from tank_backend.pipeline.queue import ThreadedQueue


class CollectorProcessor(Processor):
    """Test processor that collects items."""

    def __init__(self, name: str):
        super().__init__(name)
        self.collected: list = []

    async def process(self, item):
        self.collected.append(item)
        await asyncio.sleep(0.01)
        yield FlowReturn.OK, f"processed_{item}"


class FailingProcessor(Processor):
    """Processor that always raises."""

    def __init__(self, name: str):
        super().__init__(name)

    async def process(self, item):
        raise RuntimeError("simulated failure")
        yield  # pragma: no cover


class TestQueueQsize:
    def test_qsize_empty(self):
        q = ThreadedQueue(name="q", maxsize=5)
        assert q.qsize == 0

    def test_qsize_after_push(self):
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        q.push("a")
        q.push("b")
        assert q.qsize == 2


class TestQueueHealth:
    def test_health_initial(self):
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        h = q.health()
        assert isinstance(h, QueueHealth)
        assert h.name == "q"
        assert h.size == 0
        assert h.maxsize == 5
        assert h.last_consumed_at is None
        assert h.is_stuck is False
        assert h.consumer_alive is False

    def test_health_consumer_alive(self):
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        q.start()
        try:
            time.sleep(0.1)
            h = q.health()
            assert h.consumer_alive is True
        finally:
            q.stop()

    def test_health_last_consumed_at_updates(self):
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        q.start()
        try:
            q.push("item")
            time.sleep(0.2)
            h = q.health()
            assert h.last_consumed_at is not None
            assert h.last_consumed_at > 0
        finally:
            q.stop()

    def test_health_not_stuck_when_empty(self):
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        h = q.health(stuck_threshold_s=0.0)
        assert h.is_stuck is False

    def test_health_stuck_detection(self):
        """Queue should report stuck if items sit unconsumed beyond threshold."""
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        # Push without starting consumer
        q.push("stuck_item")
        # Set _last_consumed_at to simulate old consumption
        q._last_consumed_at = time.monotonic() - 20.0
        h = q.health(stuck_threshold_s=10.0)
        assert h.is_stuck is True


class TestQueueBlockUnblock:
    def test_push_returns_flushing_when_blocked(self):
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        q.block()
        result = q.push("item")
        assert result == FlowReturn.FLUSHING

    def test_push_works_after_unblock(self):
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        q.block()
        assert q.push("a") == FlowReturn.FLUSHING
        q.unblock()
        assert q.push("b") == FlowReturn.OK

    def test_block_does_not_affect_existing_items(self):
        """Blocking should not drain existing items."""
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        q.push("before_block")
        q.block()
        assert q.qsize == 1  # item still there


class TestConsecutiveFailures:
    def test_failures_increment(self):
        q = ThreadedQueue(name="q", maxsize=5)
        proc = FailingProcessor("fail")
        q.link(proc)
        q.start()
        try:
            q.push("item1")
            q.push("item2")
            q.push("item3")
            time.sleep(0.5)
            assert q._consecutive_failures >= 3
        finally:
            q.stop()

    def test_failures_reset_on_success(self):
        """Consecutive failures should reset after a successful process."""
        q = ThreadedQueue(name="q", maxsize=5)
        proc = CollectorProcessor("c")
        q.link(proc)
        q._consecutive_failures = 5  # Simulate prior failures
        q.start()
        try:
            q.push("item")
            time.sleep(0.2)
            assert q._consecutive_failures == 0
        finally:
            q.stop()
