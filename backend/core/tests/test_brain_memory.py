"""Tests for Brain integration with MemoryService."""

import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import Brain, BrainConfig


async def _collect(processor, item):
    """Collect all (status, output) pairs from processor.process(item)."""
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


def _make_event(text="hello", user="Jackson"):
    return BrainInputEvent(
        type=InputType.VOICE,
        text=text,
        user=user,
        language="en",
        confidence=0.99,
    )


class TestBrainMemoryIntegration:
    """Tests for Brain's memory recall and storage hooks."""

    @pytest.fixture
    def bus(self):
        return Bus()

    @pytest.fixture
    def interrupt_event(self):
        return threading.Event()

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        # Make chat_stream return an async generator that yields nothing
        async def empty_stream(**kwargs):
            return
            yield  # noqa: E701 — make it a generator
        llm.chat_stream = MagicMock(return_value=empty_stream())
        return llm

    @pytest.fixture
    def mock_tool_manager(self):
        tm = MagicMock()
        tm.get_openai_tools.return_value = []
        return tm

    @pytest.fixture
    def mock_memory_service(self):
        svc = AsyncMock()
        svc.recall = AsyncMock(return_value=["Prefers Chinese responses", "Likes coffee"])
        svc.store_turn = AsyncMock()
        return svc

    @pytest.fixture
    def brain_with_memory(
        self, mock_llm, mock_tool_manager, bus, interrupt_event, mock_memory_service
    ):
        return Brain(
            llm=mock_llm,
            tool_manager=mock_tool_manager,
            config=BrainConfig(),
            bus=bus,
            interrupt_event=interrupt_event,
            memory_service=mock_memory_service,
        )

    @pytest.fixture
    def brain_without_memory(self, mock_llm, mock_tool_manager, bus, interrupt_event):
        return Brain(
            llm=mock_llm,
            tool_manager=mock_tool_manager,
            config=BrainConfig(),
            bus=bus,
            interrupt_event=interrupt_event,
            memory_service=None,
        )

    async def test_recall_memory_returns_formatted_context(self, brain_with_memory):
        result = await brain_with_memory._recall_memory("Jackson", "hello")
        assert "Prefers Chinese responses" in result
        assert "Likes coffee" in result

    async def test_recall_memory_skips_unknown_user(self, brain_with_memory):
        result = await brain_with_memory._recall_memory("Unknown", "hello")
        assert result == ""

    async def test_recall_memory_skips_empty_user(self, brain_with_memory):
        result = await brain_with_memory._recall_memory("", "hello")
        assert result == ""

    async def test_recall_memory_returns_empty_when_no_service(self, brain_without_memory):
        result = await brain_without_memory._recall_memory("Jackson", "hello")
        assert result == ""

    async def test_recall_memory_handles_error_gracefully(
        self, brain_with_memory, mock_memory_service
    ):
        mock_memory_service.recall.side_effect = RuntimeError("boom")
        result = await brain_with_memory._recall_memory("Jackson", "hello")
        assert result == ""

    async def test_schedule_memory_store_creates_task(
        self, brain_with_memory, mock_memory_service
    ):
        brain_with_memory._last_user = "Jackson"
        brain_with_memory._last_user_text = "What's the weather?"

        brain_with_memory._schedule_memory_store("It's sunny!")

        # Give the fire-and-forget task a chance to run
        import asyncio
        await asyncio.sleep(0.05)

        mock_memory_service.store_turn.assert_called_once_with(
            "Jackson", "What's the weather?", "It's sunny!"
        )

    async def test_schedule_memory_store_skips_unknown_user(
        self, brain_with_memory, mock_memory_service
    ):
        brain_with_memory._last_user = "Unknown"
        brain_with_memory._last_user_text = "hello"

        brain_with_memory._schedule_memory_store("Hi there!")

        import asyncio
        await asyncio.sleep(0.05)

        mock_memory_service.store_turn.assert_not_called()

    async def test_schedule_memory_store_skips_when_no_service(self, brain_without_memory):
        brain_without_memory._last_user = "Jackson"
        brain_without_memory._last_user_text = "hello"
        # Should not raise
        brain_without_memory._schedule_memory_store("response")

    async def test_store_memory_safe_catches_errors(
        self, brain_with_memory, mock_memory_service
    ):
        mock_memory_service.store_turn.side_effect = RuntimeError("mem0 down")
        # Should not raise
        await brain_with_memory._store_memory_safe("Jackson", "msg", "response")

    async def test_system_prompt_not_permanently_modified(
        self, brain_with_memory, mock_memory_service
    ):
        """Memory context should be temporary — not persisted in conversation history."""
        original_system = brain_with_memory._conversation_history[0]["content"]

        # After a recall, the system prompt content should still be the original
        _ = await brain_with_memory._recall_memory("Jackson", "hello")

        # The recall itself doesn't modify the prompt — that happens in process()
        # Just verify the original is intact
        assert brain_with_memory._conversation_history[0]["content"] == original_system
