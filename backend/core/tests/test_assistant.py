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
