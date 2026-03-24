"""Tests for Brain as a native pipeline Processor."""

import threading
from unittest.mock import MagicMock

import pytest

from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processor import FlowReturn, Processor
from tank_backend.pipeline.processors.brain import Brain, BrainConfig


async def _collect(processor, item):
    """Collect all (status, output) pairs from processor.process(item)."""
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


class TestBrain:
    """Unit tests for Brain."""

    @pytest.fixture
    def bus(self):
        return Bus()

    @pytest.fixture
    def interrupt_event(self):
        return threading.Event()

    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_config(self):
        return BrainConfig()

    @pytest.fixture
    def brain(self, mock_llm, mock_tool_manager, mock_config, bus, interrupt_event):
        return Brain(
            llm=mock_llm,
            tool_manager=mock_tool_manager,
            config=mock_config,
            bus=bus,
            interrupt_event=interrupt_event,
        )

    def test_brain_inherits_from_processor(self, brain):
        """Brain should inherit from Processor."""
        assert isinstance(brain, Processor)

    def test_brain_has_name_brain(self, brain):
        """Brain processor should be named 'brain'."""
        assert brain.name == "brain"

    def test_brain_has_process_method(self, brain):
        """Brain should have async process method."""
        assert hasattr(brain, "process")
        assert callable(brain.process)

    def test_brain_loads_system_prompt(self, brain):
        """Brain should load system prompt from file."""
        assert hasattr(brain, "_system_prompt")
        assert isinstance(brain._system_prompt, str)
        assert len(brain._system_prompt) > 0
        assert "Tank" in brain._system_prompt

    def test_brain_initializes_conversation_history_with_system(self, brain):
        """Brain should initialize conversation history with system prompt as first message."""
        assert hasattr(brain, "_conversation_history")
        assert len(brain._conversation_history) == 1
        assert brain._conversation_history[0]["role"] == "system"
        assert brain._conversation_history[0]["content"] == brain._system_prompt

    async def test_brain_includes_speaker_name_in_conversation_history(
        self, brain, mock_llm
    ):
        """Brain should include speaker name in conversation history."""

        async def mock_chat_stream(*args, **kwargs):
            yield ("text", "Hello!", {})

        mock_llm.chat_stream = mock_chat_stream
        mock_llm.get_openai_tools = MagicMock(return_value=[])
        brain._tool_manager.get_openai_tools.return_value = []

        event = BrainInputEvent(
            type=InputType.TEXT,
            text="What's the weather?",
            user="Jackson",
            language="en",
            confidence=None,
        )

        await _collect(brain, event)

        assert len(brain._conversation_history) >= 2
        user_message = brain._conversation_history[1]
        assert user_message["role"] == "user"
        assert user_message["name"] == "Jackson"
        assert user_message["content"] == "What's the weather?"

    async def test_brain_handles_unknown_speaker(self, brain, mock_llm):
        """Brain should handle Unknown speaker gracefully."""

        async def mock_chat_stream(*args, **kwargs):
            yield ("text", "Hello!", {})

        mock_llm.chat_stream = mock_chat_stream
        brain._tool_manager.get_openai_tools.return_value = []

        event = BrainInputEvent(
            type=InputType.TEXT,
            text="Hello",
            user="Unknown",
            language="en",
            confidence=None,
        )

        await _collect(brain, event)

        assert len(brain._conversation_history) >= 2
        user_message = brain._conversation_history[1]
        assert user_message["role"] == "user"
        assert user_message["name"] == "Unknown"

    def test_system_prompt_includes_speaker_awareness(self, brain):
        """System prompt should mention speaker awareness."""
        assert "SPEAKER AWARENESS" in brain._system_prompt
        assert "speaker" in brain._system_prompt.lower()

    async def test_brain_skips_blank_text(self, brain, mock_llm):
        """Brain should skip events with blank text."""
        event = BrainInputEvent(
            type=InputType.TEXT,
            text="   ",
            user="User",
            language="en",
            confidence=None,
        )

        results = await _collect(brain, event)

        assert len(results) == 1
        assert results[0] == (FlowReturn.OK, None)
        mock_llm.chat_stream.assert_not_called()
