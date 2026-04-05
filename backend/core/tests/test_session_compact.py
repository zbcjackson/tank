"""Tests for session compact (wake word conversation lifecycle)."""

import threading
from unittest.mock import MagicMock

import pytest

from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processor import FlowReturn
from tank_backend.pipeline.processors.brain import Brain, BrainConfig


async def _collect(processor, item):
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


class TestBrainSessionCompact:
    """Tests for Brain compact via __compact__ system event."""

    @pytest.fixture
    def bus(self):
        return Bus()

    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def mock_config(self):
        return BrainConfig()

    @pytest.fixture
    def brain(self, mock_llm, mock_config, bus):
        return Brain(
            llm=mock_llm,
            tool_manager=MagicMock(),
            config=mock_config,
            bus=bus,
            interrupt_event=threading.Event(),
        )

    def test_reset_conversation_clears_history(self, brain):
        """reset_conversation() should keep only the system prompt."""
        brain._conversation_history.append({"role": "user", "content": "hello"})
        brain._conversation_history.append({"role": "assistant", "content": "hi there"})
        brain._conversation_history.append({"role": "user", "content": "how are you?"})
        assert len(brain._conversation_history) == 4  # system + 3

        brain.reset_conversation()

        assert len(brain._conversation_history) == 1
        assert brain._conversation_history[0]["role"] == "system"
        assert brain._conversation_history[0]["content"] == brain._system_prompt

    async def test_compact_under_budget_preserves_history(self, brain, mock_llm):
        """__compact__ with small history (under token budget) should keep all messages."""
        brain._conversation_history.append({"role": "user", "content": "hello"})
        brain._conversation_history.append({"role": "assistant", "content": "hi"})
        history_before = list(brain._conversation_history)

        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="__compact__",
            user="system",
            language=None,
            confidence=None,
        )
        results = await _collect(brain, event)

        # Under budget — history unchanged
        assert brain._conversation_history == history_before
        mock_llm.chat_stream.assert_not_called()
        assert results == [(FlowReturn.OK, None)]

    async def test_compact_does_not_emit_signals_when_under_budget(self, brain, bus):
        """__compact__ under budget should not post any UI messages to bus."""
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m.payload))

        brain._conversation_history.append({"role": "user", "content": "hello"})

        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="__compact__",
            user="system",
            language=None,
            confidence=None,
        )
        await _collect(brain, event)
        bus.poll()

        assert len(received) == 0

    async def test_handle_ignores_non_compact_system_events(self, brain, mock_llm):
        """System events with text other than __compact__ should not compact history."""
        brain._conversation_history.append({"role": "user", "content": "hello"})

        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="some_other_command",
            user="system",
            language=None,
            confidence=None,
        )
        history_before = len(brain._conversation_history)
        await _collect(brain, event)
        assert len(brain._conversation_history) >= history_before

    async def test_handle_ignores_blank_text(self, brain, mock_llm):
        """process() should ignore events with blank text."""
        event = BrainInputEvent(
            type=InputType.AUDIO,
            text="   ",
            user="User",
            language="zh",
            confidence=None,
        )
        results = await _collect(brain, event)

        mock_llm.chat_stream.assert_not_called()
        assert results == [(FlowReturn.OK, None)]
