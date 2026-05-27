"""Integration tests for ContextManager.compact() ↔ MemoryFlusher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from tank_backend.config.models import ContextConfig
from tank_backend.context.budget import ContextBudget
from tank_backend.context.conversation import ConversationData
from tank_backend.context.manager import ContextManager
from tank_backend.context.resolver import CompactionMode, ResolvedConversation


def _make_app_config():
    cfg = MagicMock()
    cfg.get_section.return_value = {}
    cfg.get_llm_profile.side_effect = KeyError("no profile")
    cfg.memory = MagicMock(enabled=False)
    cfg.preferences = MagicMock(enabled=False)
    return cfg


def _make_manager(
    *,
    config: ContextConfig | None = None,
    flusher: object | None = None,
) -> ContextManager:
    if config is None:
        config = ContextConfig(max_history_tokens=50, keep_recent_messages=2)
    budget = ContextBudget(
        context_window=config.context_window or 32_000,
        history_share=config.history_share,
        output_reserve=config.output_reserve,
        headroom=config.headroom,
    ).with_history_cap(
        config.max_history_tokens if config.max_history_tokens > 0 else None
    )

    with (
        patch.object(ContextManager, "_create_memory_service", return_value=None),
        patch.object(ContextManager, "_create_summarizer", return_value=None),
        patch.object(ContextManager, "_create_flusher", return_value=flusher),
        patch.object(ContextManager, "_resolve_budget", return_value=budget),
        patch(
            "tank_backend.prompts.assembler.PromptAssembler.assemble",
            return_value="You are helpful.",
        ),
    ):
        return ContextManager(
            app_config=_make_app_config(),
            resolver=MagicMock(),
            config=config,
        )


def _load_conversation(mgr: ContextManager) -> str:
    conv = ConversationData.new("You are helpful.")
    resolved = ResolvedConversation(
        conversation=conv, compaction_mode=CompactionMode.DESTRUCTIVE,
    )
    mgr.set_conversation(resolved)
    return conv.id


def _flood_messages(mgr: ContextManager, n: int = 20) -> None:
    for i in range(n):
        mgr.add_message("user", f"message {i}")
        mgr.add_message("assistant", f"reply {i}")


class TestPreCompactionFlushIntegration:
    async def test_flusher_called_during_compaction(self):
        flusher = MagicMock()
        flusher.flush = AsyncMock()
        mgr = _make_manager(flusher=flusher)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary"
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        # Simulate that prepare_turn has set the current speaker
        mgr._last_user = "jackson"
        _flood_messages(mgr)

        await mgr.compact()

        flusher.flush.assert_awaited_once()
        kwargs = flusher.flush.await_args.kwargs
        assert kwargs["user"] == "jackson"
        assert kwargs["messages"]
        assert all(
            "role" in m and "content" in m for m in kwargs["messages"]
        )

    async def test_no_flush_when_disabled(self):
        # Flusher is None when context.pre_compaction_flush=False or no
        # memory/preferences are wired up.
        mgr = _make_manager(flusher=None)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary"
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        mgr._last_user = "jackson"
        _flood_messages(mgr)

        # Just shouldn't raise.
        await mgr.compact()

    async def test_no_flush_when_user_unknown(self):
        # When the speaker hasn't been identified yet, the flusher needs a
        # user to write against — skip the call rather than guess.
        flusher = MagicMock()
        flusher.flush = AsyncMock()
        mgr = _make_manager(flusher=flusher)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary"
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        # Note: not setting mgr._last_user
        _flood_messages(mgr)

        await mgr.compact()
        flusher.flush.assert_not_called()

    async def test_flush_failure_does_not_block_compaction(self):
        flusher = MagicMock()
        flusher.flush = AsyncMock(side_effect=RuntimeError("LLM down"))
        mgr = _make_manager(flusher=flusher)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary text"
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        mgr._last_user = "jackson"
        _flood_messages(mgr)

        # Compaction must succeed despite the flush failure.
        await mgr.compact()
        # Confirm the summary was written into the messages.
        assert any(
            "summary text" in m.get("content", "") for m in mgr.messages
        )

    async def test_flush_runs_before_summarize(self):
        # The order of ops is critical: flush must see the original
        # messages before summarize replaces them.
        order: list[str] = []

        flusher = MagicMock()
        async def flush_recorder(**kwargs):
            order.append("flush")
            return MagicMock(is_empty=True)
        flusher.flush = flush_recorder

        summarizer = MagicMock()
        async def summarize_recorder(*args, **kwargs):
            order.append("summarize")
            return "summary"
        summarizer.summarize = summarize_recorder

        mgr = _make_manager(flusher=flusher)
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        mgr._last_user = "jackson"
        _flood_messages(mgr)

        await mgr.compact()
        assert order == ["flush", "summarize"]

    async def test_flush_skipped_when_nothing_to_summarize(self):
        # When the tail captures everything (no to_summarize), flush
        # should not be called — there's nothing about to be lost.
        flusher = MagicMock()
        flusher.flush = AsyncMock()
        # Use a config that always keeps everything in the tail.
        cfg = ContextConfig(
            max_history_tokens=10_000_000,
            keep_recent_messages=200,
        )
        mgr = _make_manager(flusher=flusher, config=cfg)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary"
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        mgr._last_user = "jackson"
        for _ in range(3):
            mgr.add_message("user", "hi")
            mgr.add_message("assistant", "hi")

        # Force a compaction with focus to bypass the under-budget guard.
        await mgr.compact(focus="x")
        # Tail consumed everything, so to_summarize is empty.
        flusher.flush.assert_not_called()
