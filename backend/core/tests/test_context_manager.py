"""Tests for context.manager — ContextManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from tank_backend.config.models import ContextConfig
from tank_backend.context.budget import ContextBudget
from tank_backend.context.conversation import ConversationData
from tank_backend.context.manager import ContextManager
from tank_backend.context.resolver import CompactionMode, ResolvedConversation
from tank_backend.llm.profile import LLMProfile


def _make_app_config():
    """Create a mock AppConfig that returns empty sections."""
    cfg = MagicMock()
    cfg.get_section.return_value = {}
    cfg.get_llm_profile.return_value = LLMProfile(
        name="default",
        api_key="test",
        model="gpt-4o",
        base_url="http://example.test",
    )
    cfg.memory = MagicMock(enabled=False)
    cfg.preferences = MagicMock(enabled=False)
    return cfg


def _make_manager(
    *,
    resolver: object | None = None,
    app_config: object | None = None,
    config: ContextConfig | None = None,
    skill_provider: object | None = None,
    budget: ContextBudget | None = None,
) -> ContextManager:
    """Create a ContextManager with mocked dependencies."""
    if app_config is None:
        app_config = _make_app_config()
    if config is None:
        config = ContextConfig()
    if resolver is None:
        resolver = MagicMock()
    if budget is None:
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
            app_config=app_config, resolver=resolver,
            config=config, skill_provider=skill_provider,
        )


def _load_conversation(
    mgr: ContextManager,
    system_prompt: str = "You are helpful.",
    mode: CompactionMode = CompactionMode.DESTRUCTIVE,
) -> str:
    """Helper: create a conversation and load it into the manager."""
    conv = ConversationData.new(system_prompt)
    resolved = ResolvedConversation(conversation=conv, compaction_mode=mode)
    mgr.set_conversation(resolved)
    return conv.id


class TestSetConversation:
    def test_loads_destructive(self):
        mgr = _make_manager()
        cid = _load_conversation(mgr)
        assert cid is not None
        assert len(cid) == 32
        assert mgr.messages[0]["role"] == "system"
        assert mgr._compaction_mode == CompactionMode.DESTRUCTIVE

    def test_loads_non_destructive(self):
        mgr = _make_manager()
        _load_conversation(mgr, mode=CompactionMode.NON_DESTRUCTIVE)
        assert mgr._compaction_mode == CompactionMode.NON_DESTRUCTIVE
        assert mgr._channel_context_builder is not None

    def test_resets_memory_context(self):
        mgr = _make_manager()
        mgr._memory_context = "old memory"
        _load_conversation(mgr)
        assert mgr._memory_context == ""


class TestMessageManagement:
    def test_add_message_appends_and_persists(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr._resolver.save.reset_mock()

        mgr.add_message("user", "hello", name="Jackson")
        assert len(mgr.messages) == 2
        assert mgr.messages[1] == {"role": "user", "content": "hello", "name": "Jackson"}
        mgr._resolver.save.assert_called_once()

    def test_messages_empty_when_no_conversation(self):
        mgr = _make_manager()
        assert mgr.messages == []


class TestPrepareTurn:
    async def test_returns_augmented_messages(self):
        def skill_provider():
            return "SKILLS: tool1"

        mgr = _make_manager(skill_provider=skill_provider)
        _load_conversation(mgr)

        messages = await mgr.prepare_turn("Jackson", "hello")
        assert any("SKILLS: tool1" in m.get("content", "") for m in messages)
        assert any(m.get("content") == "hello" for m in messages)

    async def test_does_not_mutate_stored_messages(self):
        def skill_provider():
            return "SKILLS: tool1"

        mgr = _make_manager(skill_provider=skill_provider)
        _load_conversation(mgr)

        await mgr.prepare_turn("Jackson", "hello")
        assert "SKILLS: tool1" in mgr.messages[0]["content"]

    async def test_includes_memory_context(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr._memory_facts = ["likes Python"]

        messages = await mgr.prepare_turn("Jackson", "hello")
        system_content = messages[0]["content"]
        assert "KNOWN FACTS (Jackson)" in system_content
        assert "likes Python" in system_content

    def test_finish_turn_records_turn_messages(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr._resolver.save.reset_mock()

        turn = [
            {"role": "assistant", "content": "Hi!"},
        ]
        mgr.finish_turn(turn)
        assert mgr.messages[-1]["content"] == "Hi!"
        mgr._resolver.save.assert_called_once()

    def test_finish_turn_records_tool_calls(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr._resolver.save.reset_mock()

        turn = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city":"NYC"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tc1", "content": "Sunny"},
            {"role": "assistant", "content": "It's sunny in NYC!"},
        ]
        mgr.finish_turn(turn)
        assert len(mgr.messages) == 4  # system + 3 turn messages
        mgr._resolver.save.assert_called_once()


class TestMemory:
    async def test_recall_memory_fetches(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr._memory_service = AsyncMock()
        mgr._memory_service.recall.return_value = ["likes Python", "prefers dark mode"]

        await mgr.recall_memory("Jackson", "hello")
        assert "likes Python" in mgr._memory_context

    async def test_recall_memory_handles_error(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr._memory_service = AsyncMock()
        mgr._memory_service.recall.side_effect = RuntimeError("db error")

        await mgr.recall_memory("Jackson", "hello")
        assert mgr._memory_context == ""

    async def test_recall_memory_skips_guest_user(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr._memory_service = AsyncMock()

        await mgr.recall_memory("Guest", "hello")
        mgr._memory_service.recall.assert_not_called()

    async def test_recall_memory_skips_when_no_service(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr._memory_service = None

        await mgr.recall_memory("Jackson", "hello")
        assert mgr._memory_context == ""


class TestCompaction:
    async def test_no_compact_under_budget(self):
        mgr = _make_manager(config=ContextConfig(
            max_history_tokens=100000,
            context_window=200000,
        ))
        _load_conversation(mgr)
        mgr.add_message("user", "hello")
        mgr._resolver.save.reset_mock()

        await mgr.compact()
        # No truncation needed — save not called again
        mgr._resolver.save.assert_not_called()

    async def test_truncation_when_over_budget(self):
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
        )
        mgr = _make_manager(config=config)
        _load_conversation(mgr)

        for i in range(20):
            mgr.add_message("user", f"message {i}")
            mgr.add_message("assistant", f"reply {i}")

        assert mgr.count_tokens() > mgr._budget.effective_history_tokens
        await mgr.compact()
        assert len(mgr.messages) < 42  # truncated from 1 system + 40 msgs

    async def test_summarization_when_available(self):
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
            summary_max_tokens=100,
        )
        mgr = _make_manager(config=config)

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize.return_value = "Summary of conversation"
        mgr._summarizer = mock_summarizer

        _load_conversation(mgr)
        for i in range(20):
            mgr.add_message("user", f"message {i}")
            mgr.add_message("assistant", f"reply {i}")

        await mgr.compact()
        mock_summarizer.summarize.assert_called_once()
        assert any("Summary of conversation" in m.get("content", "") for m in mgr.messages)

    async def test_fallback_to_truncation_on_summarizer_error(self):
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
        )
        mgr = _make_manager(config=config)

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize.side_effect = RuntimeError("LLM error")
        mgr._summarizer = mock_summarizer

        _load_conversation(mgr)
        for i in range(20):
            mgr.add_message("user", f"message {i}")
            mgr.add_message("assistant", f"reply {i}")

        await mgr.compact()
        assert len(mgr.messages) < 42

    async def test_compact_persists_after_modification(self):
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
        )
        mgr = _make_manager(config=config)
        _load_conversation(mgr)
        for i in range(20):
            mgr.add_message("user", f"message {i}")
            mgr.add_message("assistant", f"reply {i}")
        mgr._resolver.save.reset_mock()

        await mgr.compact()
        mgr._resolver.save.assert_called()

    async def test_compact_noop_for_non_destructive(self):
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
        )
        mgr = _make_manager(config=config)
        _load_conversation(mgr, mode=CompactionMode.NON_DESTRUCTIVE)
        for i in range(20):
            mgr.add_message("user", f"message {i}")
            mgr.add_message("assistant", f"reply {i}")
        original_count = len(mgr.messages)

        await mgr.compact()
        assert len(mgr.messages) == original_count  # no truncation

    async def test_compact_with_focus_forwards_to_summarizer(self):
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
            summary_max_tokens=100,
        )
        mgr = _make_manager(config=config)

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize.return_value = "Focused summary"
        mgr._summarizer = mock_summarizer

        _load_conversation(mgr)
        for i in range(20):
            mgr.add_message("user", f"message {i}")
            mgr.add_message("assistant", f"reply {i}")

        await mgr.compact(focus="API design")
        mock_summarizer.summarize.assert_called_once()
        kwargs = mock_summarizer.summarize.call_args.kwargs
        assert kwargs.get("focus") == "API design"

    async def test_compact_with_focus_bypasses_under_budget_guard(self):
        config = ContextConfig(
            max_history_tokens=100_000,  # huge — never triggers auto-compact
            keep_recent_messages=2,
            summary_max_tokens=100,
        )
        mgr = _make_manager(config=config)

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize.return_value = "Focused summary"
        mgr._summarizer = mock_summarizer

        _load_conversation(mgr)
        # Add enough turns that there's something to summarize after
        # the tail is carved off.
        for i in range(10):
            mgr.add_message("user", f"message {i}")
            mgr.add_message("assistant", f"reply {i}")

        # Far under budget — auto-compact would no-op, but explicit
        # focus forces it.
        assert mgr.count_tokens() < mgr._budget.effective_history_tokens
        await mgr.compact(focus="recent decisions")
        mock_summarizer.summarize.assert_called_once()

    async def test_compact_with_focus_bypasses_anti_thrashing(self):
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
            summary_max_tokens=100,
        )
        mgr = _make_manager(config=config)

        mock_summarizer = AsyncMock()
        mock_summarizer.summarize.return_value = "Focused summary"
        mgr._summarizer = mock_summarizer

        _load_conversation(mgr)
        for i in range(20):
            mgr.add_message("user", f"message {i}")
            mgr.add_message("assistant", f"reply {i}")

        # Trip the anti-thrashing guard
        mgr._ineffective_count = 5
        mgr._compaction_passes = 99

        await mgr.compact(focus="anything")
        mock_summarizer.summarize.assert_called_once()


class TestTokenCounting:
    def test_count_tokens_estimates(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        count = mgr.count_tokens()
        assert count > 0

    def test_count_tokens_with_explicit_messages(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        msgs = [{"role": "user", "content": "hello world"}]
        count = mgr.count_tokens(msgs)
        assert count > 0

    def test_count_tokens_empty(self):
        mgr = _make_manager()
        assert mgr.count_tokens([]) == 0


class TestProperties:
    def test_conversation_id_none_initially(self):
        mgr = _make_manager()
        assert mgr.conversation_id is None

    def test_conversation_id_after_set_conversation(self):
        mgr = _make_manager()
        cid = _load_conversation(mgr)
        assert mgr.conversation_id == cid

    def test_session_id_alias(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        assert mgr.session_id == mgr.conversation_id

    def test_prompt_assembler_accessible(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        assert mgr.prompt_assembler is not None

    def test_pending_approvals_none_initially(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        assert mgr.pending_approvals is None

    def test_pending_approvals_roundtrip(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr.pending_approvals = [{"id": "1", "tool": "test"}]
        assert mgr.pending_approvals == [{"id": "1", "tool": "test"}]

    def test_close_persists(self):
        mgr = _make_manager()
        _load_conversation(mgr)
        mgr._resolver.save.reset_mock()
        mgr.close()
        mgr._resolver.save.assert_called_once()

    def test_close_noop_without_conversation(self):
        mgr = _make_manager()
        mgr.close()  # should not raise


# ---------------------------------------------------------------------------
# Phase 19 follow-up: ContextManager async-init bug
# ---------------------------------------------------------------------------


class TestAsyncInitNoLoop:
    """Regression for the bug where ``ContextManager.__init__`` called
    ``asyncio.ensure_future`` from sync code without checking for a
    running loop.

    The failure mode: pytest-asyncio cleans up its event loop between
    async tests. When a later sync test (e.g. multimodal_attachments
    fixtures) builds a ``ContextManager``, ``_try_api_detect`` invoked
    ``asyncio.ensure_future`` which called
    ``asyncio.get_event_loop`` — and that raised ``RuntimeError`` in
    Python 3.13 once a loop has been closed. 4 multimodal tests
    crashed at setup time as a result.

    Fix: catch ``RuntimeError`` around ``ensure_future`` and skip the
    detection (the budget already has its model-name fallback). API
    detection is best-effort anyway; a missing event loop is a
    legitimate "skip" signal.
    """

    def test_construction_works_without_running_loop(self) -> None:
        """``ContextManager`` must be constructible from sync code
        even when no asyncio loop is running. This is the path
        pytest-asyncio leaves between async tests, and also the path
        synchronous CLI tools take when building context."""
        # Run on the real ContextManager (no _resolve_budget patch)
        # so ``_try_api_detect`` actually executes. The construction
        # used to raise ``RuntimeError: no current event loop``;
        # now it should log-and-skip and return cleanly.
        from tank_backend.llm.profile import LLMProfile

        app_config = MagicMock()
        # Provide a real LLMProfile so the get_llm_profile path
        # actually runs ``_try_api_detect``. The detection inside
        # the coroutine is what we never want to await — but we
        # still want the ``ensure_future`` call site to be reached
        # so we exercise the no-loop branch.
        app_config.get_llm_profile.return_value = LLMProfile(
            name="default",
            api_key="test",
            model="gpt-4o",
            base_url="http://example.test",
        )

        resolver = MagicMock()
        config = ContextConfig()

        with patch.object(
            ContextManager, "_create_memory_service", return_value=None,
        ), patch.object(
            ContextManager, "_create_summarizer", return_value=None,
        ), patch(
            "tank_backend.prompts.assembler.PromptAssembler.assemble",
            return_value="You are helpful.",
        ):
            # Must not raise — the no-loop branch logs at debug and
            # returns cleanly.
            mgr = ContextManager(
                app_config=app_config, resolver=resolver, config=config,
            )

        # Budget falls back to whatever ``_resolve_budget`` produced
        # without the API call.
        assert mgr.budget is not None
