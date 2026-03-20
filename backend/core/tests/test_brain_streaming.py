"""Tests for Brain streaming LLM responses as a Processor."""

import threading
from unittest.mock import MagicMock

import pytest

from tank_backend.core.events import (
    BrainInputEvent,
    DisplayMessage,
    InputType,
    UpdateType,
)
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processor import FlowReturn
from tank_backend.pipeline.processors.brain import Brain, BrainConfig


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
        yield UpdateType.THOUGHT, "Thinking...", {}
        yield UpdateType.TOOL, "", {"index": 0, "name": "get_weather", "status": "calling"}
        yield UpdateType.TOOL, "Sunny", {"index": 0, "name": "get_weather", "status": "success"}
        yield UpdateType.TEXT, "The weather is sunny.", {}

    llm.chat_stream.return_value = async_gen()
    return llm


@pytest.fixture
def brain(bus, mock_llm):
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_openai_tools.return_value = []
    config = BrainConfig()

    return Brain(
        llm=mock_llm,
        tool_manager=mock_tool_manager,
        config=config,
        bus=bus,
        interrupt_event=threading.Event(),
    )


async def test_brain_streaming_full_flow(brain, bus, mock_llm):
    event = BrainInputEvent(
        type=InputType.TEXT,
        text="What is the weather?",
        user="User",
        language="en",
        confidence=None,
        metadata={"msg_id": "test_msg_id"},
    )

    # Collect yielded outputs (AudioOutputRequest for TTS)
    results = await _collect(brain, event)

    # Collect UI messages from bus
    ui_messages = []
    bus.subscribe("ui_message", lambda m: ui_messages.append(m.payload))
    bus.poll()

    # 1. Should yield exactly one AudioOutputRequest
    assert len(results) == 1
    assert results[0][0] == FlowReturn.OK
    audio_req = results[0][1]
    assert audio_req is not None
    assert audio_req.content == "The weather is sunny."

    # 2. Assistant messages (filter out SignalMessage)
    assistant_msgs = [m for m in ui_messages if isinstance(m, DisplayMessage) and not m.is_user]
    assert any(m.update_type == UpdateType.THOUGHT for m in assistant_msgs)
    assert any(m.update_type == UpdateType.TOOL for m in assistant_msgs)
    assert any(
        m.update_type == UpdateType.TEXT and m.text == "The weather is sunny."
        for m in assistant_msgs
    )

    # 3. Final message
    assert assistant_msgs[-1].is_final is True


async def test_interrupted_response_saved_to_history(bus):
    """When Brain is interrupted mid-stream, partial text is saved to conversation history."""
    interrupt_event = threading.Event()

    # LLM streams two TEXT chunks then the interrupt fires
    async def interrupted_gen(*args, **kwargs):
        yield UpdateType.TEXT, "The weather ", {}
        yield UpdateType.TEXT, "is sunny", {}
        # Simulate interrupt being set between chunks
        interrupt_event.set()
        yield UpdateType.TEXT, " today.", {}

    mock_llm = MagicMock()
    mock_llm.chat_stream.return_value = interrupted_gen()

    mock_tool_manager = MagicMock()
    mock_tool_manager.get_openai_tools.return_value = []
    config = BrainConfig()

    brain = Brain(
        llm=mock_llm,
        tool_manager=mock_tool_manager,
        config=config,
        bus=bus,
        interrupt_event=interrupt_event,
    )

    event = BrainInputEvent(
        type=InputType.TEXT,
        text="What is the weather?",
        user="User",
        language="en",
        confidence=None,
    )

    results = await _collect(brain, event)

    # Should yield None (interrupted, no TTS)
    assert results[0][1] is None

    # Partial response should be saved in conversation history
    # History: [system, user_msg, assistant_partial]
    history = brain._conversation_history
    assistant_msgs = [m for m in history if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1
    # At least the first two chunks were accumulated before interrupt
    assert "The weather " in assistant_msgs[0]["content"]
