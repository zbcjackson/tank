"""Tests for ChannelContextBuilder — non-destructive context derivation."""

from __future__ import annotations

from typing import Any

import pytest

from tank_backend.channels.context import ChannelContextBuilder


def _make_messages(count: int, prefix: str = "msg") -> list[dict[str, Any]]:
    """Generate message list with user/assistant pairs."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": "system prompt"}]
    for i in range(count):
        messages.append({"role": "user", "content": f"{prefix}-user-{i}"})
        messages.append({"role": "assistant", "content": f"{prefix}-asst-{i}"})
    return messages


class _MockSummarizer:
    """Synchronous mock summarizer for testing."""

    def __init__(self, summary: str = "Summary of old messages"):
        self.summary = summary
        self.called_with: list[dict[str, Any]] | None = None

    async def summarize(self, messages: list[dict[str, Any]]) -> str:
        self.called_with = messages
        return self.summary


class TestContextBuilderBasics:
    def test_never_mutates_input(self):
        builder = ChannelContextBuilder(max_tokens=100000, keep_recent=5)
        messages = _make_messages(5)
        original = [dict(m) for m in messages]  # deep copy

        import asyncio

        # ``asyncio.get_event_loop()`` raises RuntimeError when there's
        # no current loop — the case in pytest-asyncio's full-suite run
        # after async tests have closed their loops. ``asyncio.run``
        # creates a fresh loop on every call, so it works regardless
        # of where this test lands in the run order.
        asyncio.run(
            builder.build(messages, "test-conv", "You are helpful."),
        )

        # Original messages unchanged
        assert messages == original

    @pytest.mark.asyncio
    async def test_passes_through_when_under_budget(self):
        builder = ChannelContextBuilder(max_tokens=100000, keep_recent=5)
        messages = _make_messages(3)

        ctx = await builder.build(messages, "test-conv", "You are helpful.")

        # System prompt + original messages
        assert ctx[0]["role"] == "system"
        assert ctx[0]["content"] == "You are helpful."
        assert len(ctx) == 1 + len(messages)

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        builder = ChannelContextBuilder()
        ctx = await builder.build([], "test-conv", "system")
        assert len(ctx) == 1
        assert ctx[0]["content"] == "system"

    @pytest.mark.asyncio
    async def test_no_system_prompt(self):
        builder = ChannelContextBuilder(max_tokens=100000)
        messages = [{"role": "user", "content": "hello"}]
        ctx = await builder.build(messages, "test-conv")
        assert len(ctx) == 1
        assert ctx[0]["content"] == "hello"


class TestContextBuilderCompaction:
    @pytest.mark.asyncio
    async def test_summarizes_old_messages(self):
        summarizer = _MockSummarizer("Condensed summary")
        # Very small budget to force compaction
        builder = ChannelContextBuilder(max_tokens=50, keep_recent=2, summarizer=summarizer)

        messages = _make_messages(10)
        ctx = await builder.build(messages, "test-conv", "You are helpful.")

        # Should have: injected system + conversation system + summary + 2 recent
        assert len(ctx) <= 6
        # Check summary message present
        summary_msgs = [m for m in ctx if "Previous conversation summary" in m.get("content", "")]
        assert len(summary_msgs) == 1
        assert "Condensed summary" in summary_msgs[0]["content"]

        # Summarizer was called with older messages (not recent ones)
        assert summarizer.called_with is not None
        assert len(summarizer.called_with) > 0

    @pytest.mark.asyncio
    async def test_preserves_recent_messages(self):
        builder = ChannelContextBuilder(max_tokens=50, keep_recent=4)
        messages = _make_messages(10)

        ctx = await builder.build(messages, "test-conv")

        # Last few messages should be preserved
        recent_contents = [m.get("content", "") for m in ctx[-4:]]
        assert "asst-9" in str(recent_contents)

    @pytest.mark.asyncio
    async def test_fallback_without_summarizer(self):
        # No summarizer — should use fallback
        builder = ChannelContextBuilder(max_tokens=50, keep_recent=2)
        messages = _make_messages(5)

        ctx = await builder.build(messages, "test-conv")

        # Should still produce a valid context (not crash)
        assert len(ctx) > 0
        # Fallback summary contains snippets
        summary_msgs = [
            m for m in ctx
            if "earlier messages" in m.get("content", "")
            or "user:" in m.get("content", "")
        ]
        # At least one summary-like message
        assert len(summary_msgs) >= 1


class TestContextBuilderCaching:
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        builder = ChannelContextBuilder(max_tokens=100000)
        messages = _make_messages(3)

        ctx1 = await builder.build(messages, "cache-test")
        ctx2 = await builder.build(messages, "cache-test")
        assert ctx1 is ctx2  # Same object (cache hit)

    @pytest.mark.asyncio
    async def test_cache_invalidation(self):
        builder = ChannelContextBuilder(max_tokens=100000)
        messages = _make_messages(3)

        ctx1 = await builder.build(messages, "inv-test")
        builder.invalidate("inv-test")
        ctx2 = await builder.build(messages, "inv-test")
        assert ctx1 is not ctx2  # Different objects (cache was invalidated)

    @pytest.mark.asyncio
    async def test_cache_miss_on_new_messages(self):
        builder = ChannelContextBuilder(max_tokens=100000)
        messages3 = _make_messages(3)
        messages5 = _make_messages(5)

        ctx1 = await builder.build(messages3, "grow-test")
        ctx2 = await builder.build(messages5, "grow-test")
        assert ctx1 is not ctx2
        assert len(ctx2) > len(ctx1)

    @pytest.mark.asyncio
    async def test_independent_caches_per_conversation(self):
        builder = ChannelContextBuilder(max_tokens=100000)
        messages = _make_messages(3)

        ctx_a = await builder.build(messages, "conv-a")
        await builder.build(messages, "conv-b")
        # Both cached independently
        ctx_a2 = await builder.build(messages, "conv-a")
        assert ctx_a is ctx_a2
