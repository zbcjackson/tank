"""Tests for context summarization in Brain."""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import Brain

MODULE = "tank_backend.pipeline.processors.brain"


def _make_brain(
    summarize_at_tokens: int = 6000,
    max_history_tokens: int = 8000,
    llm_summarization: object | None = None,
) -> Brain:
    """Create a Brain with mocked dependencies for testing summarization."""
    config = MagicMock()
    config.max_history_tokens = max_history_tokens
    config.summarize_at_tokens = summarize_at_tokens
    config.speech_interrupt_enabled = False

    llm = MagicMock()
    tool_manager = MagicMock()
    bus = Bus()

    with patch(f"{MODULE}.Brain._load_system_prompt", return_value="You are a helpful assistant."):
        brain = Brain(
            llm=llm,
            tool_manager=tool_manager,
            config=config,
            bus=bus,
            interrupt_event=threading.Event(),
            llm_summarization=llm_summarization,
        )
    return brain


class TestMaybeSummarize:
    async def test_no_summarization_below_threshold(self):
        """Should not summarize when token count is below threshold."""
        brain = _make_brain(summarize_at_tokens=50000)
        brain._add_to_conversation_history("user", "hello")
        brain._add_to_conversation_history("assistant", "hi there")

        await brain._maybe_summarize()

        # No summarization happened — still 3 messages (system + user + assistant)
        assert len(brain._conversation_history) == 3
        brain._llm.chat_completion_async.assert_not_called()

    async def test_summarization_triggered_above_threshold(self):
        """Should summarize old messages when token count exceeds threshold."""
        brain = _make_brain(summarize_at_tokens=200, max_history_tokens=10000)

        # Add enough messages to exceed 200 tokens
        for i in range(15):
            brain._add_to_conversation_history("user", f"Message {i}: " + "word " * 10)
            brain._add_to_conversation_history("assistant", f"Reply {i}: " + "response " * 10)

        # Mock the LLM summarization call
        brain._llm.chat_completion_async = AsyncMock(
            return_value={
                "choices": [{"message": {"content": "Summary of conversation."}}],
            }
        )

        old_count = len(brain._conversation_history)
        await brain._maybe_summarize()

        # Should have called LLM for summarization
        brain._llm.chat_completion_async.assert_called_once()

        # Should have fewer messages now
        assert len(brain._conversation_history) < old_count

        # System prompt should still be first
        assert brain._conversation_history[0]["role"] == "system"
        assert brain._conversation_history[0]["content"] == "You are a helpful assistant."

        # Summary message should be second
        assert brain._conversation_history[1]["role"] == "system"
        assert "Previous conversation summary:" in brain._conversation_history[1]["content"]

    async def test_summarization_preserves_last_5_messages(self):
        """Should keep the last 5 messages after summarization."""
        brain = _make_brain(summarize_at_tokens=200, max_history_tokens=10000)

        for i in range(20):
            brain._add_to_conversation_history("user", f"Message {i}: " + "word " * 10)

        brain._llm.chat_completion_async = AsyncMock(
            return_value={
                "choices": [{"message": {"content": "Summary."}}],
            }
        )

        await brain._maybe_summarize()

        # system + summary + last 5 = 7 messages
        assert len(brain._conversation_history) == 7

        # Last 5 should be the most recent messages
        last_5_contents = [m["content"] for m in brain._conversation_history[-5:]]
        for content in last_5_contents:
            assert "Message" in content

    async def test_summarization_uses_low_temperature(self):
        """Summarization LLM call should use temperature=0.3 and max_tokens=500."""
        brain = _make_brain(summarize_at_tokens=200, max_history_tokens=10000)

        for i in range(15):
            brain._add_to_conversation_history("user", f"Message {i}: " + "word " * 10)
            brain._add_to_conversation_history("assistant", f"Reply {i}: " + "response " * 10)

        brain._llm.chat_completion_async = AsyncMock(
            return_value={
                "choices": [{"message": {"content": "Summary."}}],
            }
        )

        await brain._maybe_summarize()

        call_kwargs = brain._llm.chat_completion_async.call_args
        assert call_kwargs.kwargs["temperature"] == 0.3
        assert call_kwargs.kwargs["max_tokens"] == 500

    async def test_summarization_failure_is_graceful(self):
        """If summarization LLM call fails, history should remain unchanged."""
        brain = _make_brain(summarize_at_tokens=200, max_history_tokens=10000)

        for i in range(15):
            brain._add_to_conversation_history("user", f"Message {i}: " + "word " * 10)

        brain._llm.chat_completion_async = AsyncMock(side_effect=Exception("LLM error"))

        history_before = list(brain._conversation_history)
        await brain._maybe_summarize()

        # History should be unchanged after failure
        assert brain._conversation_history == history_before

    async def test_no_summarization_with_few_messages(self):
        """Should not summarize if there are 5 or fewer non-system messages."""
        brain = _make_brain(summarize_at_tokens=10)  # Very low threshold

        for i in range(5):
            brain._add_to_conversation_history("user", f"Message {i}")

        await brain._maybe_summarize()

        # Should not have called LLM — not enough messages to split
        brain._llm.chat_completion_async.assert_not_called()


class TestSummarizationLLMProfile:
    async def test_summarization_uses_dedicated_llm_when_provided(self):
        """When a dedicated summarization LLM is provided, it should be used."""
        dedicated_llm = MagicMock()
        dedicated_llm.chat_completion_async = AsyncMock(
            return_value={
                "choices": [{"message": {"content": "Dedicated summary."}}],
            }
        )

        brain = _make_brain(
            summarize_at_tokens=200,
            max_history_tokens=10000,
            llm_summarization=dedicated_llm,
        )

        for i in range(15):
            brain._add_to_conversation_history("user", f"Message {i}: " + "word " * 10)
            brain._add_to_conversation_history("assistant", f"Reply {i}: " + "response " * 10)

        await brain._maybe_summarize()

        # Dedicated LLM should have been called
        dedicated_llm.chat_completion_async.assert_called_once()
        # Conversation LLM should NOT have been called
        brain._llm.chat_completion_async.assert_not_called()

    async def test_summarization_falls_back_to_conversation_llm(self):
        """When no dedicated summarization LLM is provided, conversation LLM is used."""
        brain = _make_brain(
            summarize_at_tokens=200,
            max_history_tokens=10000,
            llm_summarization=None,
        )

        for i in range(15):
            brain._add_to_conversation_history("user", f"Message {i}: " + "word " * 10)
            brain._add_to_conversation_history("assistant", f"Reply {i}: " + "response " * 10)

        brain._llm.chat_completion_async = AsyncMock(
            return_value={
                "choices": [{"message": {"content": "Fallback summary."}}],
            }
        )

        await brain._maybe_summarize()

        # Conversation LLM should have been called as fallback
        brain._llm.chat_completion_async.assert_called_once()
