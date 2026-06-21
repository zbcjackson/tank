"""Tests for Brain as a native pipeline Processor."""

import threading
from unittest.mock import MagicMock

import pytest
from brain_test_helpers import make_brain, make_mock_context

from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processor import FlowReturn, Processor
from tank_backend.pipeline.processors.brain import BrainConfig


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
    def mock_context(self):
        return make_mock_context()

    @pytest.fixture
    def brain(self, mock_llm, mock_tool_manager, mock_config, bus, interrupt_event, mock_context):
        return make_brain(
            llm=mock_llm,
            tool_manager=mock_tool_manager,
            config=mock_config,
            bus=bus,
            interrupt_event=interrupt_event,
            context=mock_context,
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

    def test_brain_has_context(self, brain, mock_context):
        """Brain should have a context manager."""
        assert brain._context is mock_context

    def test_brain_initializes_with_context_messages(self, brain, mock_context):
        """Brain should use context for conversation history."""
        assert mock_context.set_conversation.called
        assert len(mock_context.messages) == 1
        assert mock_context.messages[0]["role"] == "system"

    async def test_brain_includes_speaker_name_via_context(
        self, brain, mock_llm, mock_context
    ):
        """Brain should pass speaker name to context.prepare_turn."""
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

        mock_context.prepare_turn.assert_called_once()
        call_args = mock_context.prepare_turn.call_args
        assert call_args[0][0] == "Jackson"
        assert call_args[0][1] == "What's the weather?"

    async def test_brain_handles_unknown_speaker(self, brain, mock_llm, mock_context):
        """Brain should handle Unknown speaker gracefully."""
        brain._tool_manager.get_openai_tools.return_value = []

        event = BrainInputEvent(
            type=InputType.TEXT,
            text="Hello",
            user="Unknown",
            language="en",
            confidence=None,
        )

        await _collect(brain, event)

        mock_context.prepare_turn.assert_called_once()
        call_args = mock_context.prepare_turn.call_args
        assert call_args[0][0] == "Unknown"

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

    async def test_brain_discards_self_echo_from_audio(self, brain, bus):
        """Audio (ASR) transcripts that echo recent TTS should be discarded."""
        echo_text = "the weather today is sunny and warm with a gentle breeze blowing"
        brain._echo_detector.record_tts(echo_text)

        discarded = []
        bus.subscribe("echo_discarded", lambda msg: discarded.append(msg))

        event = BrainInputEvent(
            type=InputType.AUDIO,
            text=echo_text,
            user="User",
            language="en",
            confidence=None,
        )

        results = await _collect(brain, event)
        bus.poll()

        assert results[0] == (FlowReturn.OK, None)
        assert len(discarded) == 1
        assert discarded[0].payload["reason"] == "self_echo"

    async def test_brain_does_not_apply_echo_guard_to_text_input(
        self, brain, bus, mock_context
    ):
        """Typed text (ChatMode) never travels through the mic, so the echo
        guard must not discard it even if it matches recent TTS."""
        brain._tool_manager.get_openai_tools.return_value = []
        echo_text = "the weather today is sunny and warm with a gentle breeze blowing"
        brain._echo_detector.record_tts(echo_text)

        discarded = []
        bus.subscribe("echo_discarded", lambda msg: discarded.append(msg))

        event = BrainInputEvent(
            type=InputType.TEXT,
            text=echo_text,
            user="User",
            language="en",
            confidence=None,
        )

        await _collect(brain, event)
        bus.poll()

        assert len(discarded) == 0
        mock_context.prepare_turn.assert_called_once()
