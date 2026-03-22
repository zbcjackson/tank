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

    def __init__(self, tokens: list[str]):
        super().__init__("chat")
        self._tokens = tokens

    async def run(self, state):
        for tok in self._tokens:
            yield AgentOutput(type=AgentOutputType.TOKEN, content=tok, metadata={"turn": 1})
        yield AgentOutput(type=AgentOutputType.DONE)


class MockRouter(Agent):
    def __init__(self, target: str = "chat"):
        super().__init__("router")
        self._target = target

    async def run(self, state):
        yield AgentOutput(type=AgentOutputType.HANDOFF, target_agent=self._target)


def _make_brain(agent_graph=None, tts_enabled=True):
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
        """When agent_graph is set, Brain should route through agents."""
        chat_agent = MockChatAgent(["Hello", " world"])
        router = MockRouter("chat")
        graph = AgentGraph(agents={"chat": chat_agent}, router=router)

        brain, bus = _make_brain(agent_graph=graph)

        # Collect bus messages
        messages = []
        bus.subscribe("ui_message", lambda m: messages.append(m))

        event = BrainInputEvent(
            type=InputType.TEXT, text="hi", user="Tester",
            language=None, confidence=None,
        )

        results = []
        async for flow, item in brain.process(event):
            results.append((flow, item))

        # Drain bus
        bus.poll()

        # Should produce an AudioOutputRequest
        audio_requests = [item for _, item in results if item is not None]
        assert len(audio_requests) == 1
        assert audio_requests[0].content == "Hello world"

        # Bus should have received DisplayMessages
        display_msgs = [
            m.payload for m in messages
            if isinstance(m.payload, DisplayMessage) and not m.payload.is_final
        ]
        token_msgs = [m for m in display_msgs if m.update_type == UpdateType.TEXT]
        assert len(token_msgs) == 2

    async def test_backward_compat_no_agent_graph(self):
        """When agent_graph is None, Brain uses direct LLM path."""
        brain, bus = _make_brain(agent_graph=None)

        # Set up LLM mock to yield text
        async def mock_chat_stream(messages, tools=None, tool_executor=None):
            yield (UpdateType.TEXT, "Direct LLM", {"turn": 1})

        brain._llm.chat_stream = mock_chat_stream

        event = BrainInputEvent(
            type=InputType.TEXT, text="hi", user="Tester",
            language=None, confidence=None,
        )

        results = []
        async for flow, item in brain.process(event):
            results.append((flow, item))

        audio_requests = [item for _, item in results if item is not None]
        assert len(audio_requests) == 1
        assert audio_requests[0].content == "Direct LLM"

    async def test_interrupt_during_agent_processing(self):
        """Interrupt event should stop agent graph processing."""

        class SlowAgent(Agent):
            def __init__(self, interrupt_event):
                super().__init__("slow")
                self._interrupt = interrupt_event

            async def run(self, state):
                yield AgentOutput(type=AgentOutputType.TOKEN, content="partial")
                # Simulate interrupt being set
                self._interrupt.set()
                yield AgentOutput(type=AgentOutputType.TOKEN, content=" more")
                yield AgentOutput(type=AgentOutputType.DONE)

        interrupt_event = threading.Event()
        slow_agent = SlowAgent(interrupt_event)
        router = MockRouter("slow")
        graph = AgentGraph(agents={"slow": slow_agent}, router=router)

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

        # Should produce None (interrupted, partial text saved)
        audio_requests = [item for _, item in results if item is not None]
        assert len(audio_requests) == 0

    async def test_no_tts_with_agent_graph(self):
        """Agent graph path should respect tts_enabled=False."""
        chat_agent = MockChatAgent(["Hello"])
        router = MockRouter("chat")
        graph = AgentGraph(agents={"chat": chat_agent}, router=router)

        brain, bus = _make_brain(agent_graph=graph, tts_enabled=False)

        event = BrainInputEvent(
            type=InputType.TEXT, text="hi", user="Tester",
            language=None, confidence=None,
        )

        results = []
        async for flow, item in brain.process(event):
            results.append((flow, item))

        # No AudioOutputRequest when TTS disabled
        audio_requests = [item for _, item in results if item is not None]
        assert len(audio_requests) == 0
