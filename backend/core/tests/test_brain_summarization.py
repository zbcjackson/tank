"""Tests for context summarization via Brain._context.maybe_compact()."""

from unittest.mock import AsyncMock, MagicMock

from brain_test_helpers import make_brain, make_mock_context


class TestMaybeCompact:
    async def test_compact_delegates_to_context(self):
        """Brain should delegate compaction to context manager."""
        ctx = make_mock_context()
        ctx.maybe_compact = AsyncMock()
        brain = make_brain(context=ctx)

        await brain._context.maybe_compact()

        ctx.maybe_compact.assert_called_once()

    async def test_compact_called_after_agent_turn(self):
        """After a successful agent turn, Brain calls context.maybe_compact()."""
        ctx = make_mock_context()
        ctx.maybe_compact = AsyncMock()
        ctx.finish_turn = MagicMock()
        ctx.schedule_memory_store = MagicMock()

        from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType
        from tank_backend.agents.graph import AgentGraph

        class SimpleAgent(Agent):
            def __init__(self):
                super().__init__("simple")

            async def run(self, state):
                yield AgentOutput(type=AgentOutputType.TOKEN, content="Hello", metadata={"turn": 1})
                yield AgentOutput(type=AgentOutputType.DONE)

        graph = AgentGraph(agents={"simple": SimpleAgent()}, default_agent="simple")
        brain = make_brain(context=ctx, agent_graph=graph)

        from tank_backend.core.events import BrainInputEvent, InputType

        event = BrainInputEvent(
            type=InputType.TEXT, text="hi", user="User",
            language="en", confidence=None,
        )

        async for _ in brain.process(event):
            pass

        ctx.maybe_compact.assert_called_once()
        ctx.finish_turn.assert_called_once_with("Hello")
