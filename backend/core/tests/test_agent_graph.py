"""Tests for AgentGraph orchestrator."""

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType, AgentState
from tank_backend.agents.graph import AgentGraph


class MockAgent(Agent):
    """Agent that yields a sequence of tokens then DONE."""

    def __init__(self, name: str, tokens: list[str]):
        super().__init__(name)
        self._tokens = tokens

    async def run(self, state):
        for tok in self._tokens:
            yield AgentOutput(type=AgentOutputType.TOKEN, content=tok)
        yield AgentOutput(type=AgentOutputType.DONE)


class MockHandoffAgent(Agent):
    """Agent that yields a few tokens then hands off to another agent."""

    def __init__(self, name: str, tokens: list[str], handoff_to: str):
        super().__init__(name)
        self._tokens = tokens
        self._handoff_to = handoff_to

    async def run(self, state):
        for tok in self._tokens:
            yield AgentOutput(type=AgentOutputType.TOKEN, content=tok)
        yield AgentOutput(type=AgentOutputType.HANDOFF, target_agent=self._handoff_to)


class TestAgentGraph:
    async def test_default_agent_flow(self):
        chat = MockAgent("chat", ["Hello", " world"])
        graph = AgentGraph(agents={"chat": chat}, default_agent="chat")

        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        outputs = [o async for o in graph.run(state)]

        tokens = [o.content for o in outputs if o.type == AgentOutputType.TOKEN]
        assert tokens == ["Hello", " world"]

    async def test_handoff_chain(self):
        """Agent A (handoff) → agent B (done)."""
        agent_a = MockHandoffAgent("A", ["step1"], handoff_to="B")
        agent_b = MockAgent("B", ["step2", "step3"])
        graph = AgentGraph(agents={"A": agent_a, "B": agent_b}, default_agent="A")

        state = AgentState()
        outputs = [o async for o in graph.run(state)]

        tokens = [o.content for o in outputs if o.type == AgentOutputType.TOKEN]
        assert tokens == ["step1", "step2", "step3"]

    async def test_max_iterations_guard(self):
        """Graph stops after max_iterations to prevent infinite loops."""

        class InfiniteHandoffAgent(Agent):
            async def run(self, state):
                yield AgentOutput(
                    type=AgentOutputType.HANDOFF, target_agent="loop"
                )

        loop_agent = InfiniteHandoffAgent("loop")
        graph = AgentGraph(
            agents={"loop": loop_agent}, default_agent="loop", max_iterations=3
        )

        state = AgentState()
        outputs = [o async for o in graph.run(state)]
        assert len(outputs) == 0
        assert len(state.agent_history) == 3

    async def test_streaming_outputs(self):
        """All non-HANDOFF/DONE outputs should stream through."""

        class ToolAgent(Agent):
            async def run(self, state):
                yield AgentOutput(type=AgentOutputType.THOUGHT, content="thinking")
                yield AgentOutput(
                    type=AgentOutputType.TOOL_CALLING, content="",
                    metadata={"name": "calc"},
                )
                yield AgentOutput(type=AgentOutputType.TOKEN, content="result")
                yield AgentOutput(type=AgentOutputType.DONE)

        graph = AgentGraph(agents={"tool": ToolAgent("tool")}, default_agent="tool")

        state = AgentState()
        outputs = [o async for o in graph.run(state)]

        types = [o.type for o in outputs]
        assert AgentOutputType.THOUGHT in types
        assert AgentOutputType.TOOL_CALLING in types
        assert AgentOutputType.TOKEN in types
        assert AgentOutputType.HANDOFF not in types
        assert AgentOutputType.DONE not in types

    async def test_unknown_handoff_target_stops(self):
        """HANDOFF to unknown agent should terminate gracefully."""

        class BadHandoffAgent(Agent):
            async def run(self, state):
                yield AgentOutput(
                    type=AgentOutputType.HANDOFF, target_agent="nonexistent"
                )

        graph = AgentGraph(
            agents={"bad": BadHandoffAgent("bad")}, default_agent="bad"
        )
        state = AgentState()
        outputs = [o async for o in graph.run(state)]
        assert len(outputs) == 0

    async def test_agent_history_tracks_execution(self):
        chat = MockAgent("chat", ["hi"])
        graph = AgentGraph(agents={"chat": chat}, default_agent="chat")

        state = AgentState()
        async for _ in graph.run(state):
            pass

        assert "chat" in state.agent_history

    async def test_agent_without_done_treated_as_complete(self):
        """Agent that yields tokens but no DONE or HANDOFF should be treated as done."""

        class NoDoneAgent(Agent):
            async def run(self, state):
                yield AgentOutput(type=AgentOutputType.TOKEN, content="hi")

        graph = AgentGraph(
            agents={"no_done": NoDoneAgent("no_done")}, default_agent="no_done"
        )

        state = AgentState()
        outputs = [o async for o in graph.run(state)]
        assert len(outputs) == 1
        assert outputs[0].content == "hi"

    async def test_unknown_default_stops(self):
        """When default agent doesn't exist, graph stops gracefully."""
        chat = MockAgent("chat", ["hi"])
        graph = AgentGraph(agents={"chat": chat}, default_agent="nonexistent")

        state = AgentState()
        outputs = [o async for o in graph.run(state)]
        assert len(outputs) == 0
