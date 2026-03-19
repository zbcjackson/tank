"""Tests for PipelineBuilder and Pipeline."""

import asyncio

import pytest

from tank_backend.pipeline.builder import PipelineBuilder
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.event import EventDirection, PipelineEvent
from tank_backend.pipeline.fan_out_queue import FanOutQueue
from tank_backend.pipeline.processor import FlowReturn, Processor


class PassthroughProcessor(Processor):
    """Test processor that passes items through."""

    def __init__(self, name: str):
        super().__init__(name)
        self.started = False
        self.stopped = False

    async def process(self, item):
        yield FlowReturn.OK, item

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class EventCapturingProcessor(Processor):
    """Test processor that captures events."""

    def __init__(self, name: str, consume: bool = False):
        super().__init__(name)
        self.events: list[PipelineEvent] = []
        self._consume = consume

    async def process(self, item):
        yield FlowReturn.OK, item

    def handle_event(self, event: PipelineEvent) -> bool:
        self.events.append(event)
        return self._consume


class TestPipelineBuilder:
    def test_build_empty_pipeline(self):
        """Builder with no processors should produce empty pipeline."""
        bus = Bus()
        builder = PipelineBuilder(bus)
        pipeline = builder.build()
        assert len(pipeline._processors) == 0
        assert len(pipeline._queues) == 0

    def test_build_single_processor(self):
        """Builder with one processor should produce one queue."""
        bus = Bus()
        builder = PipelineBuilder(bus)
        proc = PassthroughProcessor("proc1")
        builder.add(proc)
        pipeline = builder.build()

        assert len(pipeline._processors) == 1
        assert len(pipeline._queues) == 1
        assert pipeline._processors[0] is proc

    def test_build_multiple_processors(self):
        """Builder with N processors should produce N queues."""
        bus = Bus()
        builder = PipelineBuilder(bus)
        procs = [PassthroughProcessor(f"proc{i}") for i in range(3)]
        for p in procs:
            builder.add(p)
        pipeline = builder.build()

        assert len(pipeline._processors) == 3
        assert len(pipeline._queues) == 3

    def test_builder_chaining(self):
        """Builder.add should return self for chaining."""
        bus = Bus()
        builder = PipelineBuilder(bus)
        result = builder.add(PassthroughProcessor("p1"))
        assert result is builder


class TestPipeline:
    async def test_pipeline_start_stop(self):
        """Pipeline should start and stop all processors."""
        bus = Bus()
        procs = [PassthroughProcessor(f"proc{i}") for i in range(3)]
        builder = PipelineBuilder(bus)
        for p in procs:
            builder.add(p)
        pipeline = builder.build()

        await pipeline.start()
        assert pipeline.running
        for p in procs:
            assert p.started

        await pipeline.stop()
        assert not pipeline.running
        for p in procs:
            assert p.stopped

    async def test_pipeline_double_start(self):
        """Pipeline.start should be idempotent."""
        bus = Bus()
        pipeline = PipelineBuilder(bus).add(PassthroughProcessor("p")).build()
        await pipeline.start()
        await pipeline.start()  # Should not raise
        assert pipeline.running
        await pipeline.stop()

    async def test_pipeline_double_stop(self):
        """Pipeline.stop should be idempotent."""
        bus = Bus()
        pipeline = PipelineBuilder(bus).add(PassthroughProcessor("p")).build()
        await pipeline.start()
        await pipeline.stop()
        await pipeline.stop()  # Should not raise
        assert not pipeline.running

    async def test_pipeline_push_empty(self):
        """Push to empty pipeline should return ERROR."""
        bus = Bus()
        pipeline = PipelineBuilder(bus).build()
        result = pipeline.push("item")
        assert result == FlowReturn.ERROR

    async def test_pipeline_push(self):
        """Push should forward to first queue."""
        bus = Bus()
        pipeline = PipelineBuilder(bus).add(PassthroughProcessor("p")).build()
        result = pipeline.push("item")
        assert result == FlowReturn.OK

    async def test_pipeline_send_event_propagates(self):
        """send_event should propagate through all processors."""
        bus = Bus()
        procs = [EventCapturingProcessor(f"proc{i}") for i in range(3)]
        builder = PipelineBuilder(bus)
        for p in procs:
            builder.add(p)
        pipeline = builder.build()

        event = PipelineEvent(type="flush", direction=EventDirection.DOWNSTREAM, source="test")
        pipeline.send_event(event)

        for p in procs:
            assert len(p.events) == 1
            assert p.events[0].type == "flush"

    async def test_pipeline_send_event_stops_on_consume(self):
        """send_event should stop propagation when a processor consumes it."""
        bus = Bus()
        p1 = EventCapturingProcessor("p1", consume=False)
        p2 = EventCapturingProcessor("p2", consume=True)  # Consumes
        p3 = EventCapturingProcessor("p3", consume=False)

        builder = PipelineBuilder(bus)
        builder.add(p1).add(p2).add(p3)
        pipeline = builder.build()

        event = PipelineEvent(type="flush", direction=EventDirection.DOWNSTREAM)
        pipeline.send_event(event)

        assert len(p1.events) == 1
        assert len(p2.events) == 1
        assert len(p3.events) == 0  # Stopped by p2

    async def test_pipeline_bus_accessible(self):
        """Pipeline.bus should return the bus instance."""
        bus = Bus()
        pipeline = PipelineBuilder(bus).build()
        assert pipeline.bus is bus


class CollectorProcessor(Processor):
    """Test processor that collects items it processes."""

    def __init__(self, name: str):
        super().__init__(name)
        self.items: list = []

    async def process(self, item):
        self.items.append(item)
        yield FlowReturn.OK, item

    async def start(self):
        pass

    async def stop(self):
        pass


class TestPipelineBuilderFanOut:
    def test_fan_out_requires_two_branches(self):
        """fan_out with fewer than 2 branches should raise."""
        bus = Bus()
        builder = PipelineBuilder(bus)
        builder.add(PassthroughProcessor("vad"))
        with pytest.raises(ValueError, match="at least 2 branches"):
            builder.fan_out([PassthroughProcessor("only_one")])

    def test_fan_out_fan_in_builds_correct_processor_count(self):
        """fan_out/fan_in should include all branch processors plus merger."""
        bus = Bus()
        builder = PipelineBuilder(bus)
        vad = PassthroughProcessor("vad")
        asr = PassthroughProcessor("asr")
        spk = PassthroughProcessor("speaker_id")
        merger = PassthroughProcessor("merger")
        brain = PassthroughProcessor("brain")

        builder.add(vad)
        builder.fan_out([asr], [spk])
        builder.fan_in(merger)
        builder.add(brain)
        pipeline = builder.build()

        # vad + asr + spk + merger + brain = 5 processors
        assert len(pipeline._processors) == 5
        proc_names = [p.name for p in pipeline._processors]
        assert "vad" in proc_names
        assert "asr" in proc_names
        assert "speaker_id" in proc_names
        assert "merger" in proc_names
        assert "brain" in proc_names

    def test_fan_out_creates_fan_out_queue(self):
        """The queue feeding the fan-out point should be a FanOutQueue."""
        bus = Bus()
        builder = PipelineBuilder(bus)
        builder.add(PassthroughProcessor("vad"))
        builder.fan_out(
            [PassthroughProcessor("asr")],
            [PassthroughProcessor("spk")],
        )
        builder.fan_in(PassthroughProcessor("merger"))
        pipeline = builder.build()

        fan_out_queues = [q for q in pipeline._queues if isinstance(q, FanOutQueue)]
        assert len(fan_out_queues) == 1

    def test_fan_out_fan_in_chaining(self):
        """fan_out and fan_in should return builder for chaining."""
        bus = Bus()
        builder = PipelineBuilder(bus)
        builder.add(PassthroughProcessor("vad"))
        result = builder.fan_out(
            [PassthroughProcessor("a")],
            [PassthroughProcessor("b")],
        )
        assert result is builder
        result = builder.fan_in(PassthroughProcessor("merger"))
        assert result is builder

    async def test_fan_out_fan_in_start_stop(self):
        """Pipeline with fan-out/fan-in should start and stop all processors."""
        bus = Bus()
        builder = PipelineBuilder(bus)
        procs = {
            "vad": PassthroughProcessor("vad"),
            "asr": PassthroughProcessor("asr"),
            "spk": PassthroughProcessor("spk"),
            "merger": PassthroughProcessor("merger"),
            "brain": PassthroughProcessor("brain"),
        }
        builder.add(procs["vad"])
        builder.fan_out([procs["asr"]], [procs["spk"]])
        builder.fan_in(procs["merger"])
        builder.add(procs["brain"])
        pipeline = builder.build()

        await pipeline.start()
        assert pipeline.running
        for p in procs.values():
            assert p.started

        await pipeline.stop()
        assert not pipeline.running
        for p in procs.values():
            assert p.stopped

    async def test_fan_out_fan_in_data_flow(self):
        """Items should flow through fan-out branches and merge at fan-in."""
        bus = Bus()
        builder = PipelineBuilder(bus)

        vad = PassthroughProcessor("vad")
        asr = CollectorProcessor("asr")
        spk = CollectorProcessor("spk")
        merger = CollectorProcessor("merger")

        builder.add(vad)
        builder.fan_out([asr], [spk])
        builder.fan_in(merger)
        pipeline = builder.build()

        await pipeline.start()
        pipeline.push("test_item")
        await asyncio.sleep(0.3)
        await pipeline.stop()

        # Both branches should have received the item
        assert "test_item" in asr.items
        assert "test_item" in spk.items
        # Merger should have received from both branches
        assert len(merger.items) == 2  # one from each branch

    async def test_fan_out_send_event_reaches_all_processors(self):
        """send_event should reach processors in all branches."""
        bus = Bus()
        builder = PipelineBuilder(bus)

        vad = EventCapturingProcessor("vad")
        asr = EventCapturingProcessor("asr")
        spk = EventCapturingProcessor("spk")
        merger = EventCapturingProcessor("merger")

        builder.add(vad)
        builder.fan_out([asr], [spk])
        builder.fan_in(merger)
        pipeline = builder.build()

        event = PipelineEvent(type="flush", direction=EventDirection.DOWNSTREAM)
        pipeline.send_event(event)

        for p in [vad, asr, spk, merger]:
            assert len(p.events) == 1

    async def test_fan_out_flush_all(self):
        """flush_all should flush all queues including branch queues."""
        bus = Bus()
        builder = PipelineBuilder(bus)

        builder.add(PassthroughProcessor("vad"))
        builder.fan_out(
            [PassthroughProcessor("asr")],
            [PassthroughProcessor("spk")],
        )
        builder.fan_in(PassthroughProcessor("merger"))
        pipeline = builder.build()

        # Should not raise
        pipeline.flush_all()

    def test_fan_out_with_multi_processor_branches(self):
        """Branches can have multiple processors chained."""
        bus = Bus()
        builder = PipelineBuilder(bus)

        builder.add(PassthroughProcessor("vad"))
        builder.fan_out(
            [PassthroughProcessor("asr_pre"), PassthroughProcessor("asr")],
            [PassthroughProcessor("spk")],
        )
        builder.fan_in(PassthroughProcessor("merger"))
        pipeline = builder.build()

        # vad + asr_pre + asr + spk + merger = 5
        assert len(pipeline._processors) == 5
