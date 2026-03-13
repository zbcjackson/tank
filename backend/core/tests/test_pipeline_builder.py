"""Tests for PipelineBuilder and Pipeline."""


from tank_backend.pipeline.builder import PipelineBuilder
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.event import EventDirection, PipelineEvent
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
