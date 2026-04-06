"""Tests for Brain processor with AgentGraph integration."""

import threading
from unittest.mock import MagicMock

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType
from tank_backend.agents.graph import AgentGraph
from tank_backend.core.events import BrainInputEvent, DisplayMessage, InputType, UpdateType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import Brain, BrainConfig


class MockChatAgent(Agent):
    """Agent that yields predefined tokens then DONE."""

    def __init__(self, tokens: list[str], name: str = "chat"):
        super().__init__(name)
        self._tokens = tokens

    async def run(self, state):
        for tok in self._tokens:
            yield AgentOutput(type=AgentOutputType.TOKEN, content=tok, metadata={"turn": 1})
        yield AgentOutput(type=AgentOutputType.DONE)


def _make_brain(agent_graph, tts_enabled=True):
    """Create a Brain with minimal mocks."""
    llm = MagicMock()
    tool_manager = MagicMock()
    tool_manager.get_openai_tools.return_value = []
    bus = Bus()
    interrupt_event = threading.Event()
    config = BrainConfig(max_history_tokens=8000)

    brain = Brain(
        llm=llm,
        tool_manager=tool_manager,
        config=config,
        bus=bus,
        interrupt_event=interrupt_event,
        tts_enabled=tts_enabled,
        agent_graph=agent_graph,
    )
    return brain, bus


class TestBrainWithAgentGraph:
    async def test_process_via_agents_produces_audio_request(self):
        """Brain should process through agents and produce audio."""
        chat_agent = MockChatAgent(["Hello", " world"])
        graph = AgentGraph(agents={"chat": chat_agent}, default_agent="chat")

        brain, bus = _make_brain(agent_graph=graph)

        messages = []
        bus.subscribe("ui_message", lambda m: messages.append(m))

        event = BrainInputEvent(
            type=InputType.TEXT, text="hi", user="Tester",
            language=None, confidence=None,
        )

        results = []
        async for flow, item in brain.process(event):
            results.append((flow, item))

        bus.poll()

        audio_requests = [item for _, item in results if item is not None]
        assert len(audio_requests) == 1
        assert audio_requests[0].content == "Hello world"

        display_msgs = [
            m.payload for m in messages
            if isinstance(m.payload, DisplayMessage) and not m.payload.is_final
        ]
        token_msgs = [m for m in display_msgs if m.update_type == UpdateType.TEXT]
        assert len(token_msgs) == 2

    async def test_interrupt_during_agent_processing(self):
        """Interrupt event should stop agent graph processing."""

        class SlowAgent(Agent):
            def __init__(self, interrupt_event):
                super().__init__("slow")
                self._interrupt = interrupt_event

            async def run(self, state):
                yield AgentOutput(type=AgentOutputType.TOKEN, content="partial")
                self._interrupt.set()
                yield AgentOutput(type=AgentOutputType.TOKEN, content=" more")
                yield AgentOutput(type=AgentOutputType.DONE)

        interrupt_event = threading.Event()
        slow_agent = SlowAgent(interrupt_event)
        graph = AgentGraph(agents={"slow": slow_agent}, default_agent="slow")

        llm = MagicMock()
        tool_manager = MagicMock()
        tool_manager.get_openai_tools.return_value = []
        bus = Bus()
        config = BrainConfig()

        brain = Brain(
            llm=llm,
            tool_manager=tool_manager,
            config=config,
            bus=bus,
            interrupt_event=interrupt_event,
            tts_enabled=True,
            agent_graph=graph,
        )

        event = BrainInputEvent(
            type=InputType.TEXT, text="hi", user="Tester",
            language=None, confidence=None,
        )

        results = []
        async for flow, item in brain.process(event):
            results.append((flow, item))

        audio_requests = [item for _, item in results if item is not None]
        assert len(audio_requests) == 0

    async def test_no_tts_with_agent_graph(self):
        """Agent graph path should respect tts_enabled=False."""
        chat_agent = MockChatAgent(["Hello"])
        graph = AgentGraph(agents={"chat": chat_agent}, default_agent="chat")

        brain, bus = _make_brain(agent_graph=graph, tts_enabled=False)

        event = BrainInputEvent(
            type=InputType.TEXT, text="hi", user="Tester",
            language=None, confidence=None,
        )

        results = []
        async for flow, item in brain.process(event):
            results.append((flow, item))

        audio_requests = [item for _, item in results if item is not None]
        assert len(audio_requests) == 0
