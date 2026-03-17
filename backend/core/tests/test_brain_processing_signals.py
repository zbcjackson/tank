"""Tests for Brain processing_started/ended signals via Bus."""

import threading
from unittest.mock import MagicMock

import pytest

from tank_backend.config.settings import VoiceAssistantConfig
from tank_backend.core.brain import Brain
from tank_backend.core.events import BrainInputEvent, InputType, SignalMessage, UpdateType
from tank_backend.pipeline.bus import Bus


async def _collect(processor, item):
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


@pytest.fixture
def bus():
    return Bus()


@pytest.fixture
def mock_llm():
    llm = MagicMock()

    async def async_gen(*args, **kwargs):
        yield UpdateType.TEXT, "Hello", {}

    llm.chat_stream.return_value = async_gen()
    return llm


@pytest.fixture
def brain(bus, mock_llm):
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_openai_tools.return_value = []
    config = VoiceAssistantConfig()

    return Brain(
        llm=mock_llm,
        tool_manager=mock_tool_manager,
        config=config,
        bus=bus,
        interrupt_event=threading.Event(),
    )


def _collect_ui_messages(bus):
    """Poll bus and return all ui_message payloads."""
    messages = []
    bus.subscribe("ui_message", lambda m: messages.append(m.payload))
    bus.poll()
    return messages


async def test_brain_sends_processing_started_signal(brain, bus):
    """Test that Brain sends processing_started signal when starting to process input."""
    received = []
    bus.subscribe("ui_message", lambda m: received.append(m.payload))

    event = BrainInputEvent(
        type=InputType.TEXT, text="Hello", user="User", language="en", confidence=None
    )

    await _collect(brain, event)
    bus.poll()

    signal_msgs = [m for m in received if isinstance(m, SignalMessage)]
    started_signals = [m for m in signal_msgs if m.signal_type == "processing_started"]

    assert len(started_signals) == 1, "Should send exactly one processing_started signal"
    assert started_signals[0].msg_id is not None


async def test_brain_sends_processing_ended_signal(brain, bus):
    """Test that Brain sends processing_ended signal when processing completes."""
    received = []
    bus.subscribe("ui_message", lambda m: received.append(m.payload))

    event = BrainInputEvent(
        type=InputType.TEXT, text="Hello", user="User", language="en", confidence=None
    )

    await _collect(brain, event)
    bus.poll()

    signal_msgs = [m for m in received if isinstance(m, SignalMessage)]
    ended_signals = [m for m in signal_msgs if m.signal_type == "processing_ended"]

    assert len(ended_signals) == 1, "Should send exactly one processing_ended signal"
    assert ended_signals[0].msg_id is not None


async def test_brain_signals_order(brain, bus):
    """Test that processing_started comes before processing_ended."""
    received = []
    bus.subscribe("ui_message", lambda m: received.append(m.payload))

    event = BrainInputEvent(
        type=InputType.TEXT, text="Hello", user="User", language="en", confidence=None
    )

    await _collect(brain, event)
    bus.poll()

    started_idx = next(
        (
            i
            for i, m in enumerate(received)
            if isinstance(m, SignalMessage) and m.signal_type == "processing_started"
        ),
        None,
    )
    ended_idx = next(
        (
            i
            for i, m in enumerate(received)
            if isinstance(m, SignalMessage) and m.signal_type == "processing_ended"
        ),
        None,
    )

    assert started_idx is not None, "Should have processing_started signal"
    assert ended_idx is not None, "Should have processing_ended signal"
    assert started_idx < ended_idx, "processing_started should come before processing_ended"


async def test_brain_sends_processing_ended_on_error(brain, bus, mock_llm):
    """Test that Brain sends processing_ended signal even when an error occurs."""
    received = []
    bus.subscribe("ui_message", lambda m: received.append(m.payload))

    async def error_gen(*args, **kwargs):
        raise RuntimeError("LLM error")
        yield  # unreachable

    mock_llm.chat_stream.return_value = error_gen()

    event = BrainInputEvent(
        type=InputType.TEXT, text="Hello", user="User", language="en", confidence=None
    )

    await _collect(brain, event)
    bus.poll()

    signal_msgs = [m for m in received if isinstance(m, SignalMessage)]
    ended_signals = [m for m in signal_msgs if m.signal_type == "processing_ended"]

    assert len(ended_signals) == 1, "Should send processing_ended even on error"


async def test_brain_signals_have_same_msg_id(brain, bus):
    """Test that processing_started and processing_ended share the same msg_id."""
    received = []
    bus.subscribe("ui_message", lambda m: received.append(m.payload))

    event = BrainInputEvent(
        type=InputType.TEXT, text="Hello", user="User", language="en", confidence=None
    )

    await _collect(brain, event)
    bus.poll()

    signal_msgs = [m for m in received if isinstance(m, SignalMessage)]
    started = next((m for m in signal_msgs if m.signal_type == "processing_started"), None)
    ended = next((m for m in signal_msgs if m.signal_type == "processing_ended"), None)

    assert started is not None
    assert ended is not None
    assert started.msg_id == ended.msg_id, "Both signals should have the same msg_id"
    assert started.msg_id is not None, "msg_id should not be None"
