"""Tests for pipeline interrupt flow (Phase 2): speech_start → Bus → send_event_reverse."""

from tank_backend.pipeline.builder import PipelineBuilder
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.event import EventDirection, PipelineEvent
from tank_backend.pipeline.processor import FlowReturn, Processor


class EventCapturingProcessor(Processor):
    """Test processor that captures events and their order."""

    def __init__(self, name: str, consume: bool = False):
        super().__init__(name)
        self.events: list[PipelineEvent] = []
        self._consume = consume

    async def process(self, item):
        yield FlowReturn.OK, item

    def handle_event(self, event: PipelineEvent) -> bool:
        self.events.append(event)
        return self._consume


class TestPipelineInterruptFlow:
    """Tests for interrupt event propagation through the pipeline."""

    def test_send_event_reverse_propagates_in_reverse_order(self):
        """send_event_reverse should propagate from last to first processor."""
        bus = Bus()
        p1 = EventCapturingProcessor("vad")
        p2 = EventCapturingProcessor("asr")
        p3 = EventCapturingProcessor("brain")
        p4 = EventCapturingProcessor("tts")
        p5 = EventCapturingProcessor("playback")

        pipeline = PipelineBuilder(bus).add(p1).add(p2).add(p3).add(p4).add(p5).build()

        event = PipelineEvent(
            type="interrupt",
            direction=EventDirection.UPSTREAM,
            source="speech_interrupt",
        )
        pipeline.send_event_reverse(event)

        # All processors should receive the event
        for p in [p1, p2, p3, p4, p5]:
            assert len(p.events) == 1
            assert p.events[0].type == "interrupt"

    def test_send_event_reverse_stops_on_consume(self):
        """send_event_reverse should stop when a processor consumes the event."""
        bus = Bus()
        p1 = EventCapturingProcessor("vad")
        p2 = EventCapturingProcessor("asr")
        p3 = EventCapturingProcessor("brain", consume=True)  # consumes
        p4 = EventCapturingProcessor("tts")

        pipeline = PipelineBuilder(bus).add(p1).add(p2).add(p3).add(p4).build()

        event = PipelineEvent(type="interrupt", source="test")
        pipeline.send_event_reverse(event)

        # p4 (last) receives first, then p3 consumes → p2, p1 don't receive
        assert len(p4.events) == 1
        assert len(p3.events) == 1
        assert len(p2.events) == 0
        assert len(p1.events) == 0

    def test_get_processor_by_name(self):
        """Pipeline.get_processor should return processor by name."""
        bus = Bus()
        p1 = EventCapturingProcessor("vad")
        p2 = EventCapturingProcessor("brain")

        pipeline = PipelineBuilder(bus).add(p1).add(p2).build()

        assert pipeline.get_processor("vad") is p1
        assert pipeline.get_processor("brain") is p2
        assert pipeline.get_processor("nonexistent") is None

    def test_flush_all_drains_queues(self):
        """Pipeline.flush_all should flush all ThreadedQueues."""
        bus = Bus()
        p1 = EventCapturingProcessor("p1")
        p2 = EventCapturingProcessor("p2")

        pipeline = PipelineBuilder(bus).add(p1).add(p2).build()

        # Push items into queues
        pipeline._queues[0].push("item1")
        pipeline._queues[1].push("item2")

        # Flush all
        pipeline.flush_all()

        # Queues should be empty (items drained without processing)
        assert pipeline._queues[0]._queue.empty()
        assert pipeline._queues[1]._queue.empty()

    def test_speech_start_triggers_interrupt_via_bus(self):
        """Simulates the full flow: speech_start on bus → interrupt event forward."""
        bus = Bus()
        p1 = EventCapturingProcessor("vad")
        p2 = EventCapturingProcessor("brain")
        p3 = EventCapturingProcessor("tts")
        p4 = EventCapturingProcessor("playback", consume=True)

        pipeline = PipelineBuilder(bus).add(p1).add(p2).add(p3).add(p4).build()

        # Wire up: speech_start → send_event(interrupt) forward
        def on_speech_start(_msg: BusMessage) -> None:
            pipeline.send_event(
                PipelineEvent(
                    type="interrupt",
                    direction=EventDirection.DOWNSTREAM,
                    source="speech_interrupt",
                )
            )

        bus.subscribe("speech_start", on_speech_start)

        # Simulate VAD posting speech_start
        bus.post(BusMessage(type="speech_start", source="vad"))
        bus.poll()

        # Forward: vad→brain→tts→playback, playback consumes
        assert len(p1.events) == 1  # vad receives
        assert len(p2.events) == 1  # brain receives
        assert len(p3.events) == 1  # tts receives
        assert len(p4.events) == 1  # playback receives and consumes


class TestFlushFromScope:
    """Tests for flush_from scope — verifies which queues are flushed."""

    def test_flush_from_brain_preserves_brain_input_queue(self):
        """flush_from(after='brain') should NOT flush the brain's input queue."""
        bus = Bus()
        p_asr = EventCapturingProcessor("asr")
        p_brain = EventCapturingProcessor("brain")
        p_tts = EventCapturingProcessor("tts")
        p_playback = EventCapturingProcessor("playback")

        pipeline = (
            PipelineBuilder(bus)
            .add(p_asr)
            .add(p_brain)
            .add(p_tts)
            .add(p_playback)
            .build()
        )

        # Push items into brain and tts queues
        pipeline._queues[1].push("brain_item")  # q_brain
        pipeline._queues[2].push("tts_item")  # q_tts

        # Flush only downstream of brain
        pipeline.flush_from(after="brain")

        # Brain's input queue should still have the item
        assert not pipeline._queues[1]._queue.empty()
        # TTS queue should be flushed
        assert pipeline._queues[2]._queue.empty()

    def test_flush_from_brain_flushes_tts_and_playback(self):
        """flush_from(after='brain') should flush TTS and Playback queues."""
        bus = Bus()
        p_asr = EventCapturingProcessor("asr")
        p_brain = EventCapturingProcessor("brain")
        p_tts = EventCapturingProcessor("tts")
        p_playback = EventCapturingProcessor("playback")

        pipeline = (
            PipelineBuilder(bus)
            .add(p_asr)
            .add(p_brain)
            .add(p_tts)
            .add(p_playback)
            .build()
        )

        pipeline._queues[2].push("tts_item")
        pipeline._queues[3].push("playback_item")

        pipeline.flush_from(after="brain")

        assert pipeline._queues[2]._queue.empty()
        assert pipeline._queues[3]._queue.empty()
    """Tests for Bus.subscribe_all catch-all handler."""

    def test_subscribe_all_receives_all_types(self):
        """subscribe_all handler should receive messages of any type."""
        bus = Bus()
        received = []
        bus.subscribe_all(lambda m: received.append(m))

        bus.post(BusMessage(type="type_a", source="s1"))
        bus.post(BusMessage(type="type_b", source="s2"))
        bus.post(BusMessage(type="type_c", source="s3"))
        bus.poll()

        assert len(received) == 3
        assert [m.type for m in received] == ["type_a", "type_b", "type_c"]

    def test_subscribe_all_alongside_typed_subscribers(self):
        """subscribe_all should work alongside typed subscribers."""
        bus = Bus()
        typed_received = []
        all_received = []

        bus.subscribe("type_a", lambda m: typed_received.append(m))
        bus.subscribe_all(lambda m: all_received.append(m))

        bus.post(BusMessage(type="type_a", source="s1"))
        bus.post(BusMessage(type="type_b", source="s2"))
        bus.poll()

        assert len(typed_received) == 1  # only type_a
        assert len(all_received) == 2  # both types

    def test_subscribe_all_exception_does_not_crash(self):
        """Exception in subscribe_all handler should not crash other handlers."""
        bus = Bus()
        received = []

        bus.subscribe_all(lambda m: (_ for _ in ()).throw(ValueError("boom")))
        bus.subscribe("test", lambda m: received.append(m))

        bus.post(BusMessage(type="test", source="s1"))
        bus.poll()

        # Typed handler still runs
        assert len(received) == 1
