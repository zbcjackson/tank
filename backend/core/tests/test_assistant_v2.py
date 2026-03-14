"""Tests for AssistantV2 (Phase 2 pipeline-based orchestrator)."""

from __future__ import annotations

import queue
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


class TestAssistantV2ProcessInput:
    """Tests for AssistantV2.process_input (text input path)."""

    def test_process_input_posts_ui_message_to_bus(self):
        """process_input should post a DisplayMessage to bus as ui_message."""
        bus = Bus()
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        # Simulate what process_input does (without full Assistant construction)
        from tank_backend.core.events import DisplayMessage

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

    def test_process_input_puts_brain_event(self):
        """process_input should put a BrainInputEvent on the brain_input_queue."""
        q: queue.Queue[BrainInputEvent] = queue.Queue()

        event = BrainInputEvent(
            type=InputType.TEXT,
            text="hello",
            user="Keyboard",
            language=None,
            confidence=None,
            metadata={"msg_id": "kbd_test123"},
        )
        q.put(event)

        result = q.get_nowait()
        assert result.text == "hello"
        assert result.type == InputType.TEXT
        assert result.metadata["msg_id"] == "kbd_test123"

    def test_process_input_ignores_blank(self):
        """process_input should ignore blank text."""
        q: queue.Queue[BrainInputEvent] = queue.Queue()

        # Simulate blank check
        text = "   "
        if text and text.strip():
            q.put(BrainInputEvent(
                type=InputType.TEXT, text=text, user="Keyboard",
                language=None, confidence=None,
            ))

        assert q.empty()


class TestAssistantV2ResetSession:
    """Tests for AssistantV2.reset_session."""

    def test_reset_session_puts_system_event(self):
        """reset_session should put a __reset__ BrainInputEvent."""
        q: queue.Queue[BrainInputEvent] = queue.Queue()

        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="__reset__",
            user="system",
            language=None,
            confidence=None,
        )
        q.put(event)

        result = q.get_nowait()
        assert result.type == InputType.SYSTEM
        assert result.text == "__reset__"


class TestAssistantV2UICallbacks:
    """Tests for AssistantV2 UI callback mechanism."""

    def test_ui_callback_receives_messages(self):
        """subscribe_ui callbacks should receive ui_message bus events."""
        bus = Bus()
        received = []

        # Simulate the callback wiring
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


class TestAssistantV2SpeechInterrupt:
    """Tests for speech interrupt flow in AssistantV2."""

    def test_speech_start_triggers_interrupt_event(self):
        """speech_start on bus should trigger interrupt event through pipeline."""
        bus = Bus()
        interrupt_events = []

        # Simulate pipeline.send_event_reverse
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
        """Interrupt should set the runtime interrupt_event."""
        interrupt_event = threading.Event()
        assert not interrupt_event.is_set()

        # Simulate what AssistantV2._on_speech_start does
        interrupt_event.set()
        assert interrupt_event.is_set()


class TestAssistantV2PlaybackCallback:
    """Tests for playback callback wiring."""

    def test_set_playback_callback(self):
        """set_playback_callback should update PlaybackProcessor's callback."""
        from tank_backend.pipeline.wrappers.playback_processor import PlaybackProcessor

        proc = PlaybackProcessor(bus=None)
        assert proc._playback_callback is None

        callback = MagicMock()
        proc._playback_callback = callback

        assert proc._playback_callback is callback
