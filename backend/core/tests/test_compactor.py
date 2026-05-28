"""Unit tests for context.compactor — the 5-phase compaction algorithm.

The :class:`ContextManager` test suite covers the full integration path; these
tests exercise the compactor directly with mocked collaborators so phase
behaviour is pinned in isolation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import tiktoken

from tank_backend.config.models import ContextConfig
from tank_backend.context.budget import ContextBudget
from tank_backend.context.compaction_store import CompactionStore
from tank_backend.context.compactor import CompactionResult, Compactor
from tank_backend.context.conversation import ConversationData

_ENCODER = tiktoken.get_encoding("cl100k_base")


def _make_compactor(
    *,
    config: ContextConfig | None = None,
    budget: ContextBudget | None = None,
    compaction_store: CompactionStore | None = None,
) -> Compactor:
    cfg = config or ContextConfig()
    bdg = budget or ContextBudget(
        context_window=cfg.context_window or 32_000,
        history_share=cfg.history_share,
        output_reserve=cfg.output_reserve,
        headroom=cfg.headroom,
    ).with_history_cap(
        cfg.max_history_tokens if cfg.max_history_tokens > 0 else None
    )
    return Compactor(
        budget=bdg,
        config=cfg,
        encoder=_ENCODER,
        compaction_store=compaction_store,
    )


def _make_conv(messages: list[dict[str, object]]) -> ConversationData:
    conv = ConversationData.new("system prompt")
    conv.messages = messages
    return conv


async def test_no_op_under_budget():
    """When token usage is well under budget the compactor returns a no-op."""
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=100_000, context_window=200_000),
    )
    conv = _make_conv([
        {"role": "system", "content": "hi"},
        {"role": "user", "content": "hello"},
    ])

    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=0,
        ineffective_count=0,
        tokens_before_last_compaction=0,
        summarizer=None,
        flusher=None,
    )

    assert isinstance(result, CompactionResult)
    assert result.persisted_changes is False
    assert result.compacted_count == 0
    assert result.last_compaction_at is None
    assert result.new_compaction_passes == 0
    assert result.new_ineffective_count == 0


async def test_phase1_alone_recovers_budget():
    """Pruning duplicate tool results can bring usage under budget without summarization."""
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=200, keep_recent_messages=2),
    )
    big_payload = "duplicate tool result " * 200
    conv = _make_conv([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "what?"},
        {"role": "tool", "content": big_payload, "tool_call_id": "t1"},
        {"role": "tool", "content": big_payload, "tool_call_id": "t2"},
        {"role": "tool", "content": big_payload, "tool_call_id": "t3"},
    ])

    summarizer = AsyncMock()
    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=0,
        ineffective_count=0,
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=None,
    )

    assert result.persisted_changes is True
    assert result.compacted_count == 0
    summarizer.summarize.assert_not_called()
    # Duplicates were replaced in-place
    assert any(
        msg.get("content") == "[Duplicate tool result omitted]"
        for msg in conv.messages
    )


async def test_summarization_path_replaces_middle_with_summary():
    """When over-budget, the middle is summarized and replaced with one system message."""
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=50, keep_recent_messages=2),
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(20):
        msgs.append({"role": "user", "content": f"message {i}"})
        msgs.append({"role": "assistant", "content": f"reply {i}"})
    conv = _make_conv(msgs)

    summarizer = AsyncMock()
    summarizer.summarize.return_value = "Compressed summary"

    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=0,
        ineffective_count=0,
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=None,
    )

    assert result.persisted_changes is True
    assert result.compacted_count > 0
    summarizer.summarize.assert_called_once()
    assert any(
        m.get("metadata", {}).get("type") == "compaction_summary"
        for m in conv.messages
        if isinstance(m.get("metadata"), dict)
    )


async def test_summarizer_failure_falls_back_to_truncation():
    """When summarization raises, truncation runs and the conversation still shrinks."""
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=50, keep_recent_messages=2),
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(20):
        msgs.append({"role": "user", "content": f"message {i}"})
        msgs.append({"role": "assistant", "content": f"reply {i}"})
    conv = _make_conv(msgs)
    original_len = len(conv.messages)

    summarizer = AsyncMock()
    summarizer.summarize.side_effect = RuntimeError("LLM unavailable")

    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=0,
        ineffective_count=0,
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=None,
    )

    assert result.persisted_changes is True
    assert len(conv.messages) < original_len
    # No summary message inserted on the truncation path
    assert all(
        m.get("metadata", {}).get("type") != "compaction_summary"
        for m in conv.messages
        if isinstance(m.get("metadata"), dict)
    )


async def test_focus_bypasses_under_budget_guard():
    """A user-supplied focus forces compaction even when usage is below budget."""
    compactor = _make_compactor(
        config=ContextConfig(
            max_history_tokens=100_000,
            keep_recent_messages=2,
            context_window=200_000,
        ),
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(6):
        msgs.append({"role": "user", "content": f"q{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})
    conv = _make_conv(msgs)

    summarizer = AsyncMock()
    summarizer.summarize.return_value = "focused summary"

    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus="database schema",
        compaction_passes=0,
        ineffective_count=0,
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=None,
    )

    assert result.persisted_changes is True
    summarizer.summarize.assert_called_once()
    # focus forwarded through to summarizer
    _, kwargs = summarizer.summarize.call_args
    assert kwargs.get("focus") == "database schema"


async def test_focus_bypasses_anti_thrashing():
    """Anti-thrashing counters are ignored when ``focus`` is supplied."""
    compactor = _make_compactor(
        config=ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
            max_compaction_passes=10,
        ),
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(20):
        msgs.append({"role": "user", "content": f"q{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})
    conv = _make_conv(msgs)

    summarizer = AsyncMock()
    summarizer.summarize.return_value = "focused summary"

    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus="anything",
        # both anti-thrashing guards fully tripped
        compaction_passes=99,
        ineffective_count=5,
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=None,
    )

    assert result.persisted_changes is True
    summarizer.summarize.assert_called_once()


async def test_anti_thrashing_skip_when_ineffective():
    """When ineffective_count >= 2 (and not forced) compaction is skipped."""
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=50, keep_recent_messages=2),
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(20):
        msgs.append({"role": "user", "content": f"q{i}"})
    conv = _make_conv(msgs)
    original_len = len(conv.messages)

    summarizer = AsyncMock()
    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=0,
        ineffective_count=2,  # tripped
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=None,
    )

    assert result.persisted_changes is False
    summarizer.summarize.assert_not_called()
    assert len(conv.messages) == original_len


async def test_records_compaction_when_store_present():
    """The compaction store receives a record after a successful summarize."""
    store = MagicMock(spec=CompactionStore)
    store.latest_for_conversation.return_value = None
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=50, keep_recent_messages=2),
        compaction_store=store,
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(20):
        msgs.append({"role": "user", "content": f"q{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})
    conv = _make_conv(msgs)

    summarizer = AsyncMock()
    summarizer.summarize.return_value = "summary"

    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus="topic",
        compaction_passes=0,
        ineffective_count=0,
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=None,
    )

    assert result.persisted_changes is True
    store.save.assert_called_once()
    record = store.save.call_args.args[0]
    assert record.conversation_id == conv.id
    assert record.focus == "topic"
    assert record.tokens_before == result.tokens_before
    assert record.tokens_after == result.tokens_after


async def test_pre_compaction_flush_invoked_before_summarize():
    """The flusher receives ``to_summarize`` before the summarizer is called."""
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=50, keep_recent_messages=2),
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(20):
        msgs.append({"role": "user", "content": f"q{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})
    conv = _make_conv(msgs)

    summarizer = AsyncMock()
    summarizer.summarize.return_value = "summary"
    flusher = AsyncMock()

    await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=0,
        ineffective_count=0,
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=flusher,
    )

    flusher.flush.assert_called_once()
    _, kwargs = flusher.flush.call_args
    assert kwargs["user"] == "alice"
    assert isinstance(kwargs["messages"], list)


async def test_flusher_failure_does_not_block_summarize():
    """A failing flusher must not prevent the summarizer from running."""
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=50, keep_recent_messages=2),
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(20):
        msgs.append({"role": "user", "content": f"q{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})
    conv = _make_conv(msgs)

    summarizer = AsyncMock()
    summarizer.summarize.return_value = "summary"
    flusher = AsyncMock()
    flusher.flush.side_effect = RuntimeError("flush failed")

    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=0,
        ineffective_count=0,
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=flusher,
    )

    assert result.persisted_changes is True
    summarizer.summarize.assert_called_once()


async def test_orphan_tool_result_pruned():
    """Tool results without a matching tool_call ID are removed in phase 4."""
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=50, keep_recent_messages=2),
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    # Build enough history to cross the budget so summarization triggers
    for i in range(20):
        msgs.append({
            "role": "assistant",
            "tool_calls": [
                {"id": f"call_{i}", "function": {"name": "x", "arguments": "{}"}},
            ],
        })
        msgs.append({"role": "tool", "content": "ok", "tool_call_id": f"call_{i}"})
    # Add a dangling tool result whose call won't survive summarization
    msgs.append({"role": "tool", "content": "dangling", "tool_call_id": "ghost"})
    conv = _make_conv(msgs)

    summarizer = AsyncMock()
    summarizer.summarize.return_value = "summary"

    await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=0,
        ineffective_count=0,
        tokens_before_last_compaction=0,
        summarizer=summarizer,
        flusher=None,
    )

    # The orphan tool result is gone; tool_call_ids in the surviving messages
    # all have matching tool results.
    surviving_call_ids = {
        tc["id"]
        for msg in conv.messages
        for tc in msg.get("tool_calls", [])
    }
    surviving_result_ids = {
        msg.get("tool_call_id")
        for msg in conv.messages
        if msg.get("role") == "tool"
    }
    assert "ghost" not in surviving_result_ids
    assert surviving_result_ids.issubset(surviving_call_ids)


async def test_thrashing_resets_on_effective_compaction():
    """Effective compaction (>10% savings) resets ``ineffective_count`` to zero."""
    compactor = _make_compactor(
        config=ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
            max_compaction_passes=10,
        ),
    )
    msgs: list[dict[str, object]] = [{"role": "system", "content": "sys"}]
    for i in range(40):
        msgs.append({"role": "user", "content": f"message {i}"})
        msgs.append({"role": "assistant", "content": f"reply {i}"})
    conv = _make_conv(msgs)

    summarizer = AsyncMock()
    summarizer.summarize.return_value = "tiny summary"

    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=3,
        ineffective_count=1,
        tokens_before_last_compaction=999,
        summarizer=summarizer,
        flusher=None,
    )

    assert result.persisted_changes is True
    assert result.new_compaction_passes == 4
    # Significant savings: counter resets to 0
    assert result.new_ineffective_count == 0


async def test_no_op_returns_zero_tokens_before():
    """A no-op result reports tokens_before=0 so the manager can distinguish it."""
    compactor = _make_compactor(
        config=ContextConfig(max_history_tokens=100_000, context_window=200_000),
    )
    conv = _make_conv([
        {"role": "system", "content": "hi"},
        {"role": "user", "content": "hi"},
    ])

    result = await compactor.compact(
        conversation=conv,
        last_user="alice",
        focus=None,
        compaction_passes=2,
        ineffective_count=1,
        tokens_before_last_compaction=500,
        summarizer=None,
        flusher=None,
    )

    assert result.tokens_before == 0
    assert result.new_tokens_before_last_compaction == 500
    assert result.new_compaction_passes == 2
    assert result.new_ineffective_count == 1
