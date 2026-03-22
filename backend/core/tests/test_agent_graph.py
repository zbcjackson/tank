"""Tests for AgentGraph orchestrator."""

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType, AgentState
from tank_backend.agents.graph import AgentGraph


class MockRouter(Agent):
    """Router that always hands off to a specific agent."""

    def __init__(self, target: str):
        super().__init__("router")
        self._target = target

    async def run(self, state):
        yield AgentOutput(type=AgentOutputType.HANDOFF, target_agent=self._target)


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
    async def test_router_to_agent_flow(self):
        router = MockRouter("chat")
        chat = MockAgent("chat", ["Hello", " world"])
        graph = AgentGraph(agents={"chat": chat}, router=router)

        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        outputs = [o async for o in graph.run(state)]

        tokens = [o.content for o in outputs if o.type == AgentOutputType.TOKEN]
        assert tokens == ["Hello", " world"]

    async def test_handoff_chain(self):
        """Router → agent A (handoff) → agent B (done)."""
        router = MockRouter("A")
        agent_a = MockHandoffAgent("A", ["step1"], handoff_to="B")
        agent_b = MockAgent("B", ["step2", "step3"])
        graph = AgentGraph(agents={"A": agent_a, "B": agent_b}, router=router)

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
        router = MockRouter("loop")
        graph = AgentGraph(
            agents={"loop": loop_agent}, router=router, max_iterations=3
        )

        state = AgentState()
        outputs = [o async for o in graph.run(state)]
        # Should terminate without error; no TOKEN/DONE outputs expected
        assert len(outputs) == 0

        # History should show 3 iterations (router + 2 loop handoffs)
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

        router = MockRouter("tool")
        graph = AgentGraph(agents={"tool": ToolAgent("tool")}, router=router)

        state = AgentState()
        outputs = [o async for o in graph.run(state)]

        types = [o.type for o in outputs]
        assert AgentOutputType.THOUGHT in types
        assert AgentOutputType.TOOL_CALLING in types
        assert AgentOutputType.TOKEN in types
        # HANDOFF and DONE should NOT appear in outputs
        assert AgentOutputType.HANDOFF not in types
        assert AgentOutputType.DONE not in types

    async def test_unknown_handoff_target_stops(self):
        """HANDOFF to unknown agent should terminate gracefully."""

        class BadRouter(Agent):
            async def run(self, state):
                yield AgentOutput(
                    type=AgentOutputType.HANDOFF, target_agent="nonexistent"
                )

        graph = AgentGraph(agents={"chat": MockAgent("chat", [])}, router=BadRouter("router"))
        state = AgentState()
        outputs = [o async for o in graph.run(state)]
        assert len(outputs) == 0

    async def test_agent_history_tracks_execution(self):
        router = MockRouter("chat")
        chat = MockAgent("chat", ["hi"])
        graph = AgentGraph(agents={"chat": chat}, router=router)

        state = AgentState()
        async for _ in graph.run(state):
            pass

        assert "router" in state.agent_history
        assert "chat" in state.agent_history

    async def test_agent_without_done_treated_as_complete(self):
        """Agent that yields tokens but no DONE or HANDOFF should be treated as done."""

        class NoDoneAgent(Agent):
            async def run(self, state):
                yield AgentOutput(type=AgentOutputType.TOKEN, content="hi")
                # No DONE yield

        router = MockRouter("no_done")
        graph = AgentGraph(
            agents={"no_done": NoDoneAgent("no_done")}, router=router
        )

        state = AgentState()
        outputs = [o async for o in graph.run(state)]
        assert len(outputs) == 1
        assert outputs[0].content == "hi"
