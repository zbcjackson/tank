"""Tests for Brain processing_started/ended signals."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from tank_backend.core.brain import Brain
from tank_backend.core.events import BrainInputEvent, InputType, UpdateType, SignalMessage
from tank_backend.core.runtime import RuntimeContext
from tank_backend.core.shutdown import GracefulShutdown
from tank_backend.config.settings import VoiceAssistantConfig


@pytest.fixture
def runtime():
    return RuntimeContext.create()


@pytest.fixture
def mock_llm():
    llm = MagicMock()

    async def async_gen(*args, **kwargs):
        yield UpdateType.TEXT, "Hello", {}

    llm.chat_stream.return_value = async_gen()
    return llm


@pytest.fixture
def brain(runtime, mock_llm):
    shutdown_signal = GracefulShutdown()
    mock_speaker = MagicMock()
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_openai_tools.return_value = []
    config = VoiceAssistantConfig(llm_api_key="test")

    b = Brain(shutdown_signal, runtime, mock_speaker, mock_llm, mock_tool_manager, config)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    b._event_loop = loop
    yield b
    loop.close()


def test_brain_sends_processing_started_signal(brain, runtime):
    """Test that Brain sends processing_started signal when starting to process input."""
    event = BrainInputEvent(
        type=InputType.TEXT,
        text="Hello",
        user="User",
        language="en",
        confidence=None
    )

    brain.handle(event)

    # Collect all messages
    messages = []
    while not runtime.ui_queue.empty():
        messages.append(runtime.ui_queue.get_nowait())

    # Find processing_started signal
    signal_msgs = [m for m in messages if isinstance(m, SignalMessage)]
    started_signals = [m for m in signal_msgs if m.signal_type == "processing_started"]

    assert len(started_signals) == 1, "Should send exactly one processing_started signal"
    assert started_signals[0].msg_id is not None


def test_brain_sends_processing_ended_signal(brain, runtime):
    """Test that Brain sends processing_ended signal when processing completes."""
    event = BrainInputEvent(
        type=InputType.TEXT,
        text="Hello",
        user="User",
        language="en",
        confidence=None
    )

    brain.handle(event)

    # Collect all messages
    messages = []
    while not runtime.ui_queue.empty():
        messages.append(runtime.ui_queue.get_nowait())

    # Find processing_ended signal
    signal_msgs = [m for m in messages if isinstance(m, SignalMessage)]
    ended_signals = [m for m in signal_msgs if m.signal_type == "processing_ended"]

    assert len(ended_signals) == 1, "Should send exactly one processing_ended signal"
    assert ended_signals[0].msg_id is not None


def test_brain_signals_order(brain, runtime):
    """Test that processing_started comes before processing_ended."""
    event = BrainInputEvent(
        type=InputType.TEXT,
        text="Hello",
        user="User",
        language="en",
        confidence=None
    )

    brain.handle(event)

    # Collect all messages
    messages = []
    while not runtime.ui_queue.empty():
        messages.append(runtime.ui_queue.get_nowait())

    # Find signal positions
    started_idx = next((i for i, m in enumerate(messages) if isinstance(m, SignalMessage) and m.signal_type == "processing_started"), None)
    ended_idx = next((i for i, m in enumerate(messages) if isinstance(m, SignalMessage) and m.signal_type == "processing_ended"), None)

    assert started_idx is not None, "Should have processing_started signal"
    assert ended_idx is not None, "Should have processing_ended signal"
    assert started_idx < ended_idx, "processing_started should come before processing_ended"


def test_brain_sends_processing_ended_on_error(brain, runtime, mock_llm):
    """Test that Brain sends processing_ended signal even when an error occurs."""
    # Make LLM raise an error
    async def error_gen(*args, **kwargs):
        raise RuntimeError("LLM error")
        yield  # unreachable

    mock_llm.chat_stream.return_value = error_gen()

    event = BrainInputEvent(
        type=InputType.TEXT,
        text="Hello",
        user="User",
        language="en",
        confidence=None
    )

    brain.handle(event)

    # Collect all messages
    messages = []
    while not runtime.ui_queue.empty():
        messages.append(runtime.ui_queue.get_nowait())

    # Should still have processing_ended signal
    signal_msgs = [m for m in messages if isinstance(m, SignalMessage)]
    ended_signals = [m for m in signal_msgs if m.signal_type == "processing_ended"]

    assert len(ended_signals) == 1, "Should send processing_ended even on error"


def test_brain_signals_have_same_msg_id(brain, runtime):
    """Test that processing_started and processing_ended share the same msg_id."""
    event = BrainInputEvent(
        type=InputType.TEXT,
        text="Hello",
        user="User",
        language="en",
        confidence=None
    )

    brain.handle(event)

    # Collect all messages
    messages = []
    while not runtime.ui_queue.empty():
        messages.append(runtime.ui_queue.get_nowait())

    # Find signals
    signal_msgs = [m for m in messages if isinstance(m, SignalMessage)]
    started = next((m for m in signal_msgs if m.signal_type == "processing_started"), None)
    ended = next((m for m in signal_msgs if m.signal_type == "processing_ended"), None)

    assert started is not None
    assert ended is not None
    assert started.msg_id == ended.msg_id, "Both signals should have the same msg_id"
    assert started.msg_id is not None, "msg_id should not be None"
