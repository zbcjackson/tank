"""Tests for compaction lineage integration in ContextManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from tank_backend.config.models import ContextConfig
from tank_backend.context.budget import ContextBudget
from tank_backend.context.compaction_store import CompactionStore
from tank_backend.context.compactions import CompactionRecord
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


def _make_manager_with_store(
    *,
    compaction_store: CompactionStore | None,
    config: ContextConfig | None = None,
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
            compaction_store=compaction_store,
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


class TestCompactionLineage:
    async def test_writes_record_when_store_wired(self):
        store = MagicMock(spec=CompactionStore)
        store.latest_for_conversation.return_value = None
        mgr = _make_manager_with_store(compaction_store=store)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary text"
        mgr._summarizer = summarizer

        conv_id = _load_conversation(mgr)
        _flood_messages(mgr)

        await mgr.compact()

        store.save.assert_called_once()
        record = store.save.call_args.args[0]
        assert isinstance(record, CompactionRecord)
        assert record.conversation_id == conv_id
        assert record.parent_id is None
        assert record.summary_text == "summary text"
        assert record.compacted_count > 0
        assert record.tokens_before > record.tokens_after
        assert record.pre_compaction_messages
        # The summarized messages should match what was replaced.
        assert all(
            "role" in m and "content" in m for m in record.pre_compaction_messages
        )

    async def test_no_record_when_store_is_none(self):
        mgr = _make_manager_with_store(compaction_store=None)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary text"
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        _flood_messages(mgr)

        # Just shouldn't raise.
        await mgr.compact()
        # Verify the summary actually replaced the messages
        assert any(
            "summary text" in m.get("content", "") for m in mgr.messages
        )

    async def test_record_chains_via_parent_id(self):
        store = MagicMock(spec=CompactionStore)
        # Simulate that the second call sees a previously-saved record.
        first_record = CompactionRecord(
            id="parent-1",
            conversation_id="ignored",
            parent_id=None,
            created_at=MagicMock(),
            focus=None,
            tokens_before=1000,
            tokens_after=500,
            compacted_count=10,
            summary_text="prev",
            pre_compaction_messages=[],
        )
        store.latest_for_conversation.side_effect = [None, first_record]
        mgr = _make_manager_with_store(compaction_store=store)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary"
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        _flood_messages(mgr)
        await mgr.compact()

        # Reset the thrashing state and force another compaction.
        mgr._ineffective_count = 0
        mgr._compaction_passes = 0
        _flood_messages(mgr, n=15)
        await mgr.compact()

        assert store.save.call_count == 2
        second_record = store.save.call_args_list[1].args[0]
        assert second_record.parent_id == "parent-1"

    async def test_save_failure_does_not_break_compact(self):
        store = MagicMock(spec=CompactionStore)
        store.latest_for_conversation.return_value = None
        store.save.side_effect = RuntimeError("disk full")
        mgr = _make_manager_with_store(compaction_store=store)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary"
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        _flood_messages(mgr)

        # Compaction must still succeed despite the store failure.
        await mgr.compact()
        assert any(
            "summary" in m.get("content", "") for m in mgr.messages
        )

    async def test_focus_propagates_to_record(self):
        store = MagicMock(spec=CompactionStore)
        store.latest_for_conversation.return_value = None
        mgr = _make_manager_with_store(compaction_store=store)

        summarizer = AsyncMock()
        summarizer.summarize.return_value = "summary"
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        _flood_messages(mgr)

        await mgr.compact(focus="API design")
        record = store.save.call_args.args[0]
        assert record.focus == "API design"

    async def test_no_record_on_summarizer_failure(self):
        # When summarization throws, we fall back to truncation. There's
        # no summary text to save, so no lineage record is written.
        store = MagicMock(spec=CompactionStore)
        store.latest_for_conversation.return_value = None
        mgr = _make_manager_with_store(compaction_store=store)

        summarizer = AsyncMock()
        summarizer.summarize.side_effect = RuntimeError("LLM error")
        mgr._summarizer = summarizer

        _load_conversation(mgr)
        _flood_messages(mgr)

        await mgr.compact()
        store.save.assert_not_called()
