"""Tests for token counting and history truncation in Brain."""

import threading
from unittest.mock import MagicMock, patch

import tiktoken

from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import Brain

MODULE = "tank_backend.pipeline.processors.brain"

# Use the same encoder Brain uses internally
_encoder = tiktoken.get_encoding("cl100k_base")


def _token_count(text: str) -> int:
    """Count tokens in a string using cl100k_base."""
    return len(_encoder.encode(text))


def _make_brain(max_history_tokens: int = 8000) -> Brain:
    """Create a Brain with mocked dependencies for testing history management."""
    config = MagicMock()
    config.max_history_tokens = max_history_tokens

    llm = MagicMock()
    tool_manager = MagicMock()
    bus = Bus()

    # Mock system prompt to match what tests expect
    mock_prompt = "You are a helpful assistant."
    with patch(f"{MODULE}.Brain._load_system_prompt", return_value=mock_prompt):
        brain = Brain(
            llm=llm,
            tool_manager=tool_manager,
            config=config,
            bus=bus,
            interrupt_event=threading.Event(),
        )
    return brain


class TestCountTokens:
    def test_empty_messages(self):
        brain = _make_brain()
        assert brain._count_tokens([]) == 0

    def test_single_message(self):
        brain = _make_brain()
        messages = [{"role": "user", "content": "hello"}]
        count = brain._count_tokens(messages)
        # "hello" is 1 token + 4 overhead = 5
        assert count == _token_count("hello") + 4

    def test_multiple_messages(self):
        brain = _make_brain()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
        ]
        count = brain._count_tokens(messages)
        expected = sum(_token_count(m["content"]) + 4 for m in messages)
        assert count == expected

    def test_none_content(self):
        brain = _make_brain()
        messages = [{"role": "assistant", "content": None}]
        count = brain._count_tokens(messages)
        # None content → 0 content tokens + 4 overhead
        assert count == 4

    def test_chinese_text(self):
        brain = _make_brain()
        messages = [{"role": "user", "content": "你好世界"}]
        count = brain._count_tokens(messages)
        assert count > 4  # Chinese chars use more tokens than ASCII


class TestTruncateHistory:
    """Tests for _truncate_history (the fallback compaction strategy)."""

    def test_no_truncation_within_budget(self):
        brain = _make_brain(max_history_tokens=8000)
        brain._add_to_conversation_history("user", "hello")
        brain._add_to_conversation_history("assistant", "hi there")
        brain._truncate_history(8000)
        # System prompt + 2 messages should be well within 8000 tokens
        assert len(brain._conversation_history) == 3

    def test_system_prompt_always_kept(self):
        brain = _make_brain(max_history_tokens=100)
        for i in range(50):
            brain._add_to_conversation_history("user", f"Message number {i} " * 10)
        brain._truncate_history(100)
        # System prompt should always be first
        assert brain._conversation_history[0]["role"] == "system"
        assert "You are a helpful assistant." in brain._conversation_history[0]["content"]

    def test_recent_messages_preserved(self):
        brain = _make_brain(max_history_tokens=200)
        for i in range(20):
            brain._add_to_conversation_history("user", f"Message {i} with some padding text")
        brain._truncate_history(200)
        # The most recent message should always be present
        assert any("Message 19" in str(m.get("content", "")) for m in brain._conversation_history)

    def test_old_messages_dropped(self):
        brain = _make_brain(max_history_tokens=200)
        brain._add_to_conversation_history("user", "very old message")
        for i in range(20):
            brain._add_to_conversation_history("user", f"Newer message {i} with padding text")
        brain._truncate_history(200)
        contents = [str(m.get("content", "")) for m in brain._conversation_history]
        assert not any("very old message" in c for c in contents)

    def test_truncation_respects_token_budget(self):
        budget = 300
        brain = _make_brain(max_history_tokens=budget)
        for i in range(30):
            brain._add_to_conversation_history("user", f"Turn {i}: " + "word " * 20)
        brain._truncate_history(budget)
        total = brain._count_tokens(brain._conversation_history)
        assert total <= budget

    def test_small_budget_keeps_at_least_system_and_last(self):
        """Even with a very tight budget, system prompt + last message should be kept."""
        brain = _make_brain(max_history_tokens=50)
        brain._add_to_conversation_history("user", "hi")
        brain._truncate_history(50)
        # Should have at least system + the last message
        assert len(brain._conversation_history) >= 2
        assert brain._conversation_history[0]["role"] == "system"


class TestAddToConversationHistory:
    """_add_to_conversation_history is now a simple append."""

    def test_appends_message(self):
        brain = _make_brain()
        brain._add_to_conversation_history("user", "hello")
        assert len(brain._conversation_history) == 2  # system + user
        assert brain._conversation_history[1] == {"role": "user", "content": "hello"}

    def test_appends_message_with_name(self):
        brain = _make_brain()
        brain._add_to_conversation_history("user", "hello", name="Jackson")
        assert len(brain._conversation_history) == 2
        assert brain._conversation_history[1] == {
            "role": "user",
            "content": "hello",
            "name": "Jackson",
        }

    def test_does_not_truncate(self):
        """Append should never truncate — compaction is a separate step."""
        brain = _make_brain(max_history_tokens=50)
        for i in range(50):
            brain._add_to_conversation_history("user", f"Message {i} " * 10)
        # All 51 messages should be present (system + 50 user)
        assert len(brain._conversation_history) == 51
