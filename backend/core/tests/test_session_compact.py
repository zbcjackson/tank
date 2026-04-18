"""Tests for session compact (wake word conversation lifecycle)."""

from unittest.mock import MagicMock

import pytest
from brain_test_helpers import make_brain, make_mock_context

from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processor import FlowReturn
from tank_backend.pipeline.processors.brain import BrainConfig


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
    def mock_context(self):
        return make_mock_context()

    @pytest.fixture
    def brain(self, mock_llm, mock_config, bus, mock_context):
        return make_brain(
            llm=mock_llm,
            config=mock_config,
            bus=bus,
            context=mock_context,
        )

    def test_reset_conversation_delegates_to_context(self, brain, mock_context):
        """reset_conversation() should delegate to context.clear()."""
        brain.reset_conversation()
        mock_context.clear.assert_called_once()

    async def test_compact_delegates_to_context(self, brain, mock_llm, mock_context):
        """__compact__ should delegate to context.compact()."""
        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="__compact__",
            user="system",
            language=None,
            confidence=None,
        )
        results = await _collect(brain, event)

        mock_context.compact.assert_called_once()
        mock_llm.chat_stream.assert_not_called()
        assert results == [(FlowReturn.OK, None)]

    async def test_compact_does_not_emit_signals(self, brain, bus, mock_context):
        """__compact__ should not post any UI messages to bus."""
        received = []
        bus.subscribe("ui_message", lambda m: received.append(m.payload))

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
        event = BrainInputEvent(
            type=InputType.SYSTEM,
            text="some_other_command",
            user="system",
            language=None,
            confidence=None,
        )
        await _collect(brain, event)

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
