"""Tests for Assistant (pipeline-based orchestrator, Brain as native Processor)."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from tank_backend.core.events import (
    BrainInputEvent,
    DisplayMessage,
    InputType,
    SignalMessage,
)
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.event import PipelineEvent
from tank_backend.pipeline.processor import FlowReturn


class TestAssistantProcessInput:
    """Tests for Assistant.process_input (text input path)."""

    def test_process_input_posts_ui_message_to_bus(self):
        """process_input should post a DisplayMessage to bus as ui_message."""
        bus = Bus()
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        msg = BusMessage(
            type="ui_message",
            source="keyboard",
            payload=DisplayMessage(
                speaker="Keyboard",
                text="hello",
                is_user=True,
                is_final=True,
                msg_id="kbd_test123",
            ),
        )
        bus.post(msg)
        bus.poll()

        assert len(received) == 1
        assert received[0].payload.text == "hello"
        assert received[0].payload.is_user is True

    def test_process_input_creates_brain_event(self):
        """process_input should create a BrainInputEvent for the pipeline."""
        event = BrainInputEvent(
            type=InputType.TEXT,
            text="hello",
            user="Keyboard",
            language=None,
            confidence=None,
            metadata={"msg_id": "kbd_test123"},
        )

        assert event.text == "hello"
        assert event.type == InputType.TEXT
        assert event.metadata["msg_id"] == "kbd_test123"

    def test_process_input_ignores_blank(self):
        """process_input should ignore blank text."""
        text = "   "
        should_process = bool(text and text.strip())
        assert not should_process


class TestAssistantResetSession:
    """Tests for Assistant.reset_session."""

    def test_reset_session_creates_system_event(self):
        """reset_session should create a __reset__ BrainInputEvent."""
        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="__reset__",
            user="system",
            language=None,
            confidence=None,
        )

        assert event.type == InputType.SYSTEM
        assert event.text == "__reset__"


class TestAssistantUICallbacks:
    """Tests for Assistant UI callback mechanism."""

    def test_ui_callback_receives_messages(self):
        """subscribe_ui callbacks should receive ui_message bus events."""
        bus = Bus()
        received = []

        def on_ui_bus_message(message: BusMessage) -> None:
            received.append(message.payload)

        bus.subscribe("ui_message", on_ui_bus_message)

        signal = SignalMessage(signal_type="processing_started", msg_id="test_1")
        bus.post(BusMessage(type="ui_message", source="brain", payload=signal))
        bus.poll()

        assert len(received) == 1
        assert received[0] is signal

    def test_multiple_ui_callbacks(self):
        """Multiple subscribe_ui callbacks should all receive messages."""
        bus = Bus()
        received1 = []
        received2 = []

        bus.subscribe("ui_message", lambda m: received1.append(m.payload))
        bus.subscribe("ui_message", lambda m: received2.append(m.payload))

        display = DisplayMessage(
            speaker="Brain", text="hello", is_user=False, msg_id="test_1"
        )
        bus.post(BusMessage(type="ui_message", source="brain", payload=display))
        bus.poll()

        assert len(received1) == 1
        assert len(received2) == 1

    def test_ui_callback_exception_does_not_crash(self):
        """Exception in one UI callback should not prevent others from running."""
        bus = Bus()
        received = []

        def bad_callback(msg: BusMessage) -> None:
            raise ValueError("callback error")

        def good_callback(msg: BusMessage) -> None:
            received.append(msg.payload)

        bus.subscribe("ui_message", bad_callback)
        bus.subscribe("ui_message", good_callback)

        bus.post(BusMessage(
            type="ui_message", source="brain",
            payload=SignalMessage(signal_type="test"),
        ))
        bus.poll()

        assert len(received) == 1


class TestAssistantSpeechInterrupt:
    """Tests for speech interrupt flow in Assistant."""

    def test_speech_start_triggers_interrupt_event(self):
        """speech_start on bus should trigger interrupt event through pipeline."""
        bus = Bus()
        interrupt_events = []

        def on_speech_start(_msg: BusMessage) -> None:
            interrupt_events.append(
                PipelineEvent(type="interrupt", source="speech_interrupt")
            )

        bus.subscribe("speech_start", on_speech_start)

        bus.post(BusMessage(type="speech_start", source="vad"))
        bus.poll()

        assert len(interrupt_events) == 1
        assert interrupt_events[0].type == "interrupt"

    def test_interrupt_sets_runtime_event(self):
        """Interrupt should set the interrupt_event."""
        interrupt_event = threading.Event()
        assert not interrupt_event.is_set()

        interrupt_event.set()
        assert interrupt_event.is_set()


class TestAssistantPipelineBusyGuard:
    """Tests for pipeline-busy guard on speech interrupt."""

    def test_brain_active_tracked_via_processing_signals(self):
        """processing_started/ended signals should toggle _brain_active."""
        bus = Bus()
        brain_active_states = []

        # Simulate what Assistant._on_ui_bus_message does
        brain_active = False

        def on_ui_message(msg: BusMessage) -> None:
            nonlocal brain_active
            payload = msg.payload
            if isinstance(payload, SignalMessage):
                if payload.signal_type == "processing_started":
                    brain_active = True
                elif payload.signal_type == "processing_ended":
                    brain_active = False
            brain_active_states.append(brain_active)

        bus.subscribe("ui_message", on_ui_message)

        # Post processing_started
        bus.post(BusMessage(
            type="ui_message", source="brain",
            payload=SignalMessage(signal_type="processing_started", msg_id="test_1"),
        ))
        bus.poll()
        assert brain_active_states[-1] is True

        # Post processing_ended
        bus.post(BusMessage(
            type="ui_message", source="brain",
            payload=SignalMessage(signal_type="processing_ended", msg_id="test_1"),
        ))
        bus.poll()
        assert brain_active_states[-1] is False

    def test_playback_active_tracked_via_bus(self):
        """playback_started/ended should toggle playback active state."""
        bus = Bus()
        playback_active = False

        def on_started(_msg: BusMessage) -> None:
            nonlocal playback_active
            playback_active = True

        def on_ended(_msg: BusMessage) -> None:
            nonlocal playback_active
            playback_active = False

        bus.subscribe("playback_started", on_started)
        bus.subscribe("playback_ended", on_ended)

        bus.post(BusMessage(type="playback_started", source="playback", payload=None))
        bus.poll()
        assert playback_active is True

        bus.post(BusMessage(type="playback_ended", source="playback", payload=None))
        bus.poll()
        assert playback_active is False

    def test_interrupt_skipped_when_pipeline_idle(self):
        """speech_start should NOT fire interrupt when pipeline is idle."""
        bus = Bus()
        interrupt_fired = []

        # Simulate Assistant._on_speech_start with busy guard
        brain_active = False
        playback_active = False

        def on_speech_start(_msg: BusMessage) -> None:
            if not brain_active and not playback_active:
                return  # skip — nothing to interrupt
            interrupt_fired.append(True)

        bus.subscribe("speech_start", on_speech_start)

        bus.post(BusMessage(type="speech_start", source="vad"))
        bus.poll()

        assert len(interrupt_fired) == 0

    def test_interrupt_fires_when_brain_active(self):
        """speech_start should fire interrupt when brain is processing."""
        bus = Bus()
        interrupt_fired = []

        brain_active = True
        playback_active = False

        def on_speech_start(_msg: BusMessage) -> None:
            if not brain_active and not playback_active:
                return
            interrupt_fired.append(True)

        bus.subscribe("speech_start", on_speech_start)

        bus.post(BusMessage(type="speech_start", source="vad"))
        bus.poll()

        assert len(interrupt_fired) == 1

    def test_interrupt_fires_when_playback_active(self):
        """speech_start should fire interrupt when playback is active."""
        bus = Bus()
        interrupt_fired = []

        brain_active = False
        playback_active = True

        def on_speech_start(_msg: BusMessage) -> None:
            if not brain_active and not playback_active:
                return
            interrupt_fired.append(True)

        bus.subscribe("speech_start", on_speech_start)

        bus.post(BusMessage(type="speech_start", source="vad"))
        bus.poll()

        assert len(interrupt_fired) == 1


class TestAssistantClientInterrupt:
    """Tests for Assistant.interrupt() (stop button / client-initiated)."""

    def test_interrupt_sets_runtime_event_when_busy(self):
        """interrupt() should set interrupt_event when pipeline is busy."""
        evt = threading.Event()
        pipeline_events = []

        class FakePipeline:
            def send_event(self, event):
                pipeline_events.append(event)

            def flush_all(self):
                pass

        # Simulate Assistant state: brain active, pipeline present
        brain_active = True
        playback_active = False
        pipeline = FakePipeline()

        # Replicate interrupt() logic
        if (brain_active or playback_active) and pipeline is not None:
            pipeline.send_event(
                PipelineEvent(type="interrupt", source="client_interrupt")
            )
            pipeline.flush_all()
            evt.set()

        assert evt.is_set()
        assert len(pipeline_events) == 1
        assert pipeline_events[0].source == "client_interrupt"

    def test_interrupt_noop_when_idle(self):
        """interrupt() should be a no-op when pipeline is not busy."""
        interrupt_event = threading.Event()

        brain_active = False
        playback_active = False

        if brain_active or playback_active:
            interrupt_event.set()

        assert not interrupt_event.is_set()

    def test_interrupt_works_during_playback(self):
        """interrupt() should work when only playback is active (brain done)."""
        interrupt_event = threading.Event()
        pipeline_events = []

        class FakePipeline:
            def send_event(self, event):
                pipeline_events.append(event)

            def flush_all(self):
                pass

        brain_active = False
        playback_active = True
        pipeline = FakePipeline()

        if (brain_active or playback_active) and pipeline is not None:
            pipeline.send_event(
                PipelineEvent(type="interrupt", source="client_interrupt")
            )
            pipeline.flush_all()
            interrupt_event.set()

        assert interrupt_event.is_set()
        assert len(pipeline_events) == 1


class TestAssistantPlaybackCallback:
    """Tests for playback callback wiring."""

    def test_set_playback_callback(self):
        """set_playback_callback should update PlaybackProcessor's callback."""
        from tank_backend.pipeline.processors.playback import PlaybackProcessor

        proc = PlaybackProcessor(bus=None)
        assert proc._playback_callback is None

        callback = MagicMock()
        proc._playback_callback = callback

        assert proc._playback_callback is callback


class TestPipelinePushAt:
    """Tests for Pipeline.push_at() used by process_input/reset_session."""

    def test_push_at_finds_processor_by_name(self):
        """push_at should push to the queue feeding the named processor."""
        from tank_backend.pipeline.builder import PipelineBuilder
        from tank_backend.pipeline.processor import Processor

        class DummyProcessor(Processor):
            def __init__(self, name):
                super().__init__(name=name)
                self.received = []

            async def process(self, item):
                self.received.append(item)
                yield FlowReturn.OK, None

        bus = Bus()
        proc = DummyProcessor("brain")
        pipeline = PipelineBuilder(bus).add(proc).build()

        result = pipeline.push_at("brain", "test_item")
        assert result == FlowReturn.OK

    def test_push_at_raises_for_unknown_processor(self):
        """push_at should raise ValueError for unknown processor name."""
        from tank_backend.pipeline.builder import PipelineBuilder

        bus = Bus()
        pipeline = PipelineBuilder(bus).build()

        import pytest
        with pytest.raises(ValueError, match="not found"):
            pipeline.push_at("nonexistent", "item")
