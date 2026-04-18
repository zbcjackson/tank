"""Tests for Brain streaming LLM responses as a Processor."""

import threading

import pytest
from brain_test_helpers import make_brain, make_mock_context

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType
from tank_backend.agents.graph import AgentGraph
from tank_backend.core.events import (
    BrainInputEvent,
    DisplayMessage,
    InputType,
    UpdateType,
)
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processor import FlowReturn


async def _collect(processor, item):
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


class _StreamingAgent(Agent):
    """Agent that yields TOOL_CALLING, TOOL_RESULT, then TOKEN events."""

    def __init__(self):
        super().__init__("streaming")

    async def run(self, state):
        yield AgentOutput(
            type=AgentOutputType.TOOL_CALLING, content="",
            metadata={"index": 0, "name": "get_weather", "status": "calling"},
        )
        yield AgentOutput(
            type=AgentOutputType.TOOL_RESULT, content="Sunny",
            metadata={"index": 0, "name": "get_weather", "status": "success"},
        )
        yield AgentOutput(
            type=AgentOutputType.TOKEN, content="The weather is sunny.",
            metadata={"turn": 1},
        )
        yield AgentOutput(type=AgentOutputType.DONE)


@pytest.fixture
def bus():
    return Bus()


@pytest.fixture
def brain(bus):
    agent = _StreamingAgent()
    graph = AgentGraph(agents={"streaming": agent}, default_agent="streaming")

    return make_brain(
        bus=bus,
        agent_graph=graph,
    )


async def test_brain_streaming_full_flow(brain, bus):
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
    assert any(m.update_type == UpdateType.TOOL for m in assistant_msgs)
    assert any(
        m.update_type == UpdateType.TEXT and m.text == "The weather is sunny."
        for m in assistant_msgs
    )

    # 3. Final message
    assert assistant_msgs[-1].is_final is True


async def test_interrupted_response_saved_to_context(bus):
    """When Brain is interrupted mid-stream, partial text is saved via context.finish_turn."""
    interrupt_event = threading.Event()

    class InterruptingAgent(Agent):
        def __init__(self, interrupt_event):
            super().__init__("interrupting")
            self._interrupt = interrupt_event

        async def run(self, state):
            yield AgentOutput(
                type=AgentOutputType.TOKEN, content="The weather ",
                metadata={"turn": 1},
            )
            yield AgentOutput(
                type=AgentOutputType.TOKEN, content="is sunny",
                metadata={"turn": 1},
            )
            # Simulate interrupt being set between chunks
            self._interrupt.set()
            yield AgentOutput(
                type=AgentOutputType.TOKEN, content=" today.",
                metadata={"turn": 1},
            )
            yield AgentOutput(type=AgentOutputType.DONE)

    agent = InterruptingAgent(interrupt_event)
    graph = AgentGraph(agents={"interrupting": agent}, default_agent="interrupting")

    ctx = make_mock_context()
    brain = make_brain(
        bus=bus,
        interrupt_event=interrupt_event,
        context=ctx,
        agent_graph=graph,
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

    # Partial response should be saved via context.finish_turn
    ctx.finish_turn.assert_called_once()
    saved_arg = ctx.finish_turn.call_args[0][0]
    # finish_turn now receives the turn_messages list
    assert isinstance(saved_arg, list)
