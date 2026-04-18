"""Tests for Brain integration with memory via ContextManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from brain_test_helpers import make_brain, make_mock_context

from tank_backend.core.events import BrainInputEvent, InputType


async def _collect(processor, item):
    """Collect all (status, output) pairs from processor.process(item)."""
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


def _make_event(text="hello", user="Jackson"):
    return BrainInputEvent(
        type=InputType.AUDIO,
        text=text,
        user=user,
        language="en",
        confidence=0.99,
    )


class TestBrainMemoryIntegration:
    """Tests for Brain's memory recall and storage via ContextManager."""

    @pytest.fixture
    def mock_context(self):
        ctx = make_mock_context()
        ctx.recall_memory = AsyncMock()
        ctx.schedule_memory_store = MagicMock()
        return ctx

    @pytest.fixture
    def brain_with_memory(self, mock_context):
        return make_brain(context=mock_context)

    async def test_recall_memory_called_during_process(self, brain_with_memory, mock_context):
        """Brain should call context.recall_memory during processing."""
        mock_context.recall_memory = AsyncMock()

        event = _make_event(text="hello", user="Jackson")
        await _collect(brain_with_memory, event)

        mock_context.recall_memory.assert_called_once_with("Jackson", "hello")

    async def test_schedule_memory_store_called_after_turn(self, mock_context):
        """Brain should call context.schedule_memory_store after a successful turn."""
        from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType
        from tank_backend.agents.graph import AgentGraph

        class SimpleAgent(Agent):
            def __init__(self):
                super().__init__("simple")

            async def run(self, state):
                yield AgentOutput(
                    type=AgentOutputType.TOKEN, content="Hi there!",
                    metadata={"turn": 1},
                )
                yield AgentOutput(type=AgentOutputType.DONE)

        graph = AgentGraph(agents={"simple": SimpleAgent()}, default_agent="simple")
        ctx = make_mock_context()
        ctx.recall_memory = AsyncMock()
        ctx.schedule_memory_store = MagicMock()
        ctx.finish_turn = MagicMock()

        brain = make_brain(context=ctx, agent_graph=graph)

        event = _make_event(text="What's the weather?", user="Jackson")
        await _collect(brain, event)

        ctx.schedule_memory_store.assert_called_once_with(
            "Jackson", "What's the weather?", "Hi there!"
        )

    async def test_memory_not_called_for_blank_text(self, brain_with_memory, mock_context):
        """Brain should not call memory for blank text events."""
        event = BrainInputEvent(
            type=InputType.TEXT,
            text="   ",
            user="Jackson",
            language="en",
            confidence=None,
        )
        await _collect(brain_with_memory, event)

        mock_context.recall_memory.assert_not_called()
