"""Tests for Brain interrupt flow — verifies new sentence is processed after interrupt."""

import threading
from unittest.mock import MagicMock

from brain_test_helpers import make_brain

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType
from tank_backend.agents.graph import AgentGraph
from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import BrainConfig


class _SlowAgent(Agent):
    """Agent that yields tokens, then waits for interrupt before yielding more."""

    def __init__(self, interrupt_event: threading.Event):
        super().__init__("slow")
        self._interrupt = interrupt_event

    async def run(self, state):
        yield AgentOutput(type=AgentOutputType.TOKEN, content="partial", metadata={"turn": 1})
        # Simulate interrupt being set mid-stream
        self._interrupt.set()
        yield AgentOutput(type=AgentOutputType.TOKEN, content=" more", metadata={"turn": 1})
        yield AgentOutput(type=AgentOutputType.DONE)


def _make_brain_with_graph(agent_graph):
    """Create a Brain with minimal mocks."""
    llm = MagicMock()
    tool_manager = MagicMock()
    tool_manager.get_openai_tools.return_value = []
    bus = Bus()
    interrupt_event = threading.Event()
    config = BrainConfig(max_history_tokens=8000)

    brain = make_brain(
        llm=llm,
        tool_manager=tool_manager,
        config=config,
        bus=bus,
        interrupt_event=interrupt_event,
        tts_enabled=True,
        agent_graph=agent_graph,
    )
    return brain, bus, interrupt_event


def _make_event(text: str) -> BrainInputEvent:
    return BrainInputEvent(
        type=InputType.TEXT,
        text=text,
        user="Tester",
        language="en",
        confidence=None,
    )


async def _collect(processor, item):
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


class TestBrainInterruptResume:
    """Verify that after interrupt, the brain processes the next sentence."""

    async def test_brain_processes_next_item_after_interrupt(self):
        """After BrainInterrupted, the next call to process() should work normally."""
        interrupt_event = threading.Event()
        slow_agent = _SlowAgent(interrupt_event)
        graph = AgentGraph(agents={"slow": slow_agent}, default_agent="slow")

        brain, bus, _ = _make_brain_with_graph(agent_graph=graph)
        brain._interrupt_event = interrupt_event

        # First event — will be interrupted
        event1 = _make_event("first sentence")
        results1 = await _collect(brain, event1)
        audio1 = [item for _, item in results1 if item is not None]
        assert len(audio1) == 0  # interrupted, no audio

        # Reset interrupt and set up a fresh agent for the second call
        interrupt_event.clear()

        class SimpleAgent(Agent):
            def __init__(self):
                super().__init__("simple")

            async def run(self, state):
                yield AgentOutput(
                    type=AgentOutputType.TOKEN, content="second response",
                    metadata={"turn": 1},
                )
                yield AgentOutput(type=AgentOutputType.DONE)

        simple_agent = SimpleAgent()
        graph2 = AgentGraph(agents={"simple": simple_agent}, default_agent="simple")
        brain._agent_graph = graph2

        # Second event — should be processed normally
        event2 = _make_event("second sentence")
        results2 = await _collect(brain, event2)
        audio2 = [item for _, item in results2 if item is not None]
        assert len(audio2) == 1
        assert audio2[0].content == "second response"


class TestProcessViaAgentsInterrupt:
    """Tests for _process_via_agents interrupt handling improvements."""

    async def test_saves_partial_response_on_interrupt(self):
        """Partial response text should be saved via context.finish_turn on interrupt."""
        interrupt_event = threading.Event()
        slow_agent = _SlowAgent(interrupt_event)
        graph = AgentGraph(agents={"slow": slow_agent}, default_agent="slow")

        brain, bus, _ = _make_brain_with_graph(agent_graph=graph)
        brain._interrupt_event = interrupt_event

        event = _make_event("hello")
        await _collect(brain, event)

        # The partial text "partial" should have been saved via context.finish_turn
        brain._context.finish_turn.assert_called_once_with("partial")

    async def test_closes_generator_on_interrupt(self):
        """The agent graph generator should be properly closed on interrupt."""
        graph_gen_closed = False
        original_run = AgentGraph.run

        async def tracking_run(self, state):
            nonlocal graph_gen_closed
            try:
                async for output in original_run(self, state):
                    yield output
            finally:
                graph_gen_closed = True

        interrupt_event = threading.Event()
        slow_agent = _SlowAgent(interrupt_event)
        graph = AgentGraph(agents={"slow": slow_agent}, default_agent="slow")
        # Monkey-patch the graph's run method to track closure
        graph.run = lambda state: tracking_run(graph, state)

        brain, bus, _ = _make_brain_with_graph(agent_graph=graph)
        brain._interrupt_event = interrupt_event

        event = _make_event("hello")
        await _collect(brain, event)

        # The generator should have been properly closed via aclose()
        assert graph_gen_closed
