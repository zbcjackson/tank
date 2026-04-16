"""Tests for context.manager — ContextManager."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from tank_backend.context.config import ContextConfig
from tank_backend.context.manager import ContextManager
from tank_backend.context.session import SessionData


def _make_app_config():
    """Create a mock AppConfig that returns empty sections."""
    cfg = MagicMock()
    cfg.get_section.return_value = {}
    cfg.get_llm_profile.side_effect = KeyError("no profile")
    return cfg


def _make_manager(
    *,
    store: object | None = MagicMock(),
    app_config: object | None = None,
    config: ContextConfig | None = None,
) -> ContextManager:
    """Create a ContextManager with mocked dependencies."""
    if app_config is None:
        app_config = _make_app_config()
    if config is None:
        config = ContextConfig(store_type="file", store_path="/tmp/test-sessions")

    with (
        patch.object(ContextManager, "_create_store", return_value=store),
        patch.object(ContextManager, "_create_memory_service", return_value=None),
        patch.object(ContextManager, "_create_summarizer", return_value=None),
        patch(
            "tank_backend.prompts.assembler.PromptAssembler.assemble",
            return_value="You are helpful.",
        ),
    ):
        return ContextManager(app_config=app_config, config=config)


class TestSessionLifecycle:
    def test_new_session_creates_with_system_prompt(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        sid = mgr.new_session()
        assert sid is not None
        assert len(sid) == 32  # UUID hex
        assert mgr.messages[0]["role"] == "system"
        store.save.assert_called_once()

    def test_resume_or_new_creates_new_when_no_store(self):
        mgr = _make_manager(store=None)
        sid = mgr.resume_or_new()
        assert sid is not None

    def test_resume_or_new_creates_new_when_no_latest(self):
        store = MagicMock()
        store.find_latest.return_value = None
        mgr = _make_manager(store=store)
        sid = mgr.resume_or_new()
        assert sid is not None
        store.find_latest.assert_called_once()

    def test_resume_or_new_resumes_same_day_session(self):
        # Use noon UTC today to avoid midnight boundary issues
        today_noon = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        existing = SessionData(
            id="existing-id",
            start_time=today_noon - timedelta(hours=1),
            pid=1,
            messages=[
                {"role": "system", "content": "old prompt"},
                {"role": "user", "content": "hello"},
            ],
        )
        store = MagicMock()
        store.find_latest.return_value = existing
        mgr = _make_manager(store=store)

        # Patch both the assembler and datetime.now so "today" matches
        with (
            patch.object(mgr._prompt_assembler, "assemble", return_value="new prompt"),
            patch(
                "tank_backend.context.manager.datetime",
                wraps=datetime,
            ) as mock_dt,
        ):
            mock_dt.now.return_value = today_noon
            sid = mgr.resume_or_new()
        assert sid == "existing-id"
        assert len(mgr.messages) == 2  # preserved messages
        # System prompt updated to current assembled version
        assert mgr.messages[0]["content"] == "new prompt"

    def test_resume_or_new_creates_new_on_different_day(self):
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        existing = SessionData(
            id="old-id",
            start_time=yesterday,
            pid=1,
            messages=[{"role": "system", "content": "old"}],
        )
        store = MagicMock()
        store.find_latest.return_value = existing
        mgr = _make_manager(store=store)

        sid = mgr.resume_or_new()
        assert sid != "old-id"  # new session created

    def test_clear_creates_new_session(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        sid1 = mgr.new_session()
        sid2 = mgr.clear()
        assert sid1 != sid2
        assert store.save.call_count == 2  # both sessions persisted

    def test_resume_session_loads_specific(self):
        existing = SessionData(
            id="target",
            start_time=datetime.now(timezone.utc),
            pid=1,
            messages=[{"role": "system", "content": "test"}],
        )
        store = MagicMock()
        store.load.return_value = existing
        mgr = _make_manager(store=store)

        assert mgr.resume_session("target")
        assert mgr.session_id == "target"

    def test_resume_session_returns_false_when_not_found(self):
        store = MagicMock()
        store.load.return_value = None
        mgr = _make_manager(store=store)

        assert not mgr.resume_session("nonexistent")


class TestMessageManagement:
    def test_add_message_appends_and_persists(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        mgr.new_session()
        store.save.reset_mock()

        mgr.add_message("user", "hello", name="Jackson")
        assert len(mgr.messages) == 2
        assert mgr.messages[1] == {"role": "user", "content": "hello", "name": "Jackson"}
        store.save.assert_called_once()

    def test_messages_empty_when_no_session(self):
        mgr = _make_manager(store=None)
        assert mgr.messages == []


class TestPrepareTurn:
    def test_returns_augmented_messages(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        mgr.new_session()

        messages = mgr.prepare_turn("Jackson", "hello", skill_catalog="SKILLS: tool1")
        # Should contain augmented system prompt + user message
        assert any("SKILLS: tool1" in m.get("content", "") for m in messages)
        assert any(m.get("content") == "hello" for m in messages)

    def test_does_not_mutate_stored_messages(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        mgr.new_session()

        mgr.prepare_turn("Jackson", "hello", skill_catalog="SKILLS: tool1")
        # Stored system prompt should NOT contain skill catalog
        assert "SKILLS" not in mgr.messages[0]["content"]

    def test_includes_memory_context(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        mgr.new_session()
        mgr._memory_context = "- likes Python"

        messages = mgr.prepare_turn("Jackson", "hello")
        system_content = messages[0]["content"]
        assert "KNOWN FACTS ABOUT Jackson" in system_content
        assert "likes Python" in system_content

    def test_finish_turn_records_response(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        mgr.new_session()
        store.save.reset_mock()

        mgr.finish_turn("Hi there!")
        assert mgr.messages[-1] == {"role": "assistant", "content": "Hi there!"}
        store.save.assert_called_once()


class TestMemory:
    async def test_recall_memory_fetches(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        mgr._memory_service = AsyncMock()
        mgr._memory_service.recall.return_value = ["likes Python", "lives in Shanghai"]

        await mgr.recall_memory("Jackson", "hello")
        assert "likes Python" in mgr._memory_context
        assert "lives in Shanghai" in mgr._memory_context

    async def test_recall_memory_handles_error(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        mgr._memory_service = AsyncMock()
        mgr._memory_service.recall.side_effect = RuntimeError("db error")

        await mgr.recall_memory("Jackson", "hello")
        assert mgr._memory_context == ""

    async def test_recall_memory_skips_unknown_user(self):
        store = MagicMock()
        mgr = _make_manager(store=store)
        mgr._memory_service = AsyncMock()

        await mgr.recall_memory("Unknown", "hello")
        mgr._memory_service.recall.assert_not_called()

    async def test_recall_memory_skips_when_no_service(self):
        mgr = _make_manager(store=None)
        await mgr.recall_memory("Jackson", "hello")
        assert mgr._memory_context == ""


class TestCompaction:
    async def test_no_compact_under_budget(self):
        store = MagicMock()
        config = ContextConfig(
            max_history_tokens=50000,
            store_type="file",
            store_path="/tmp/test",
        )
        mgr = _make_manager(store=store, config=config)
        mgr.new_session()
        mgr.add_message("user", "hello")
        store.save.reset_mock()

        await mgr.maybe_compact()
        # No compaction — store.save not called again
        store.save.assert_not_called()

    async def test_truncation_when_over_budget(self):
        store = MagicMock()
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=1,
            store_type="file",
            store_path="/tmp/test",
        )
        mgr = _make_manager(store=store, config=config)
        mgr.new_session()
        # Add many messages to exceed budget
        for i in range(20):
            mgr.add_message("user", f"message {i} " * 20)
        store.save.reset_mock()

        await mgr.maybe_compact()
        # Should have truncated — fewer messages now
        assert len(mgr.messages) < 22  # system + 20 user
        store.save.assert_called()

    async def test_summarization_when_available(self):
        store = MagicMock()
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
            store_type="file",
            store_path="/tmp/test",
        )
        mgr = _make_manager(store=store, config=config)
        mgr._summarizer = AsyncMock()
        mgr._summarizer.summarize.return_value = "Summary of conversation"
        mgr.new_session()
        for i in range(10):
            mgr.add_message("user", f"message {i} " * 20)
        store.save.reset_mock()

        await mgr.maybe_compact()
        mgr._summarizer.summarize.assert_called_once()
        # Should have system + summary + 2 recent
        assert len(mgr.messages) == 4
        assert "Summary of conversation" in mgr.messages[1]["content"]

    async def test_fallback_to_truncation_on_summarizer_error(self):
        store = MagicMock()
        config = ContextConfig(
            max_history_tokens=50,
            keep_recent_messages=2,
            store_type="file",
            store_path="/tmp/test",
        )
        mgr = _make_manager(store=store, config=config)
        mgr._summarizer = AsyncMock()
        mgr._summarizer.summarize.side_effect = RuntimeError("LLM error")
        mgr.new_session()
        for i in range(10):
            mgr.add_message("user", f"message {i} " * 20)
        store.save.reset_mock()

        await mgr.maybe_compact()
        # Should have fallen back to truncation
        assert len(mgr.messages) < 12
        store.save.assert_called()


class TestTokenCounting:
    def test_count_tokens_estimates(self):
        mgr = _make_manager(store=None)
        mgr.new_session()
        count = mgr.count_tokens()
        assert count > 0  # system prompt has tokens

    def test_count_tokens_with_explicit_messages(self):
        mgr = _make_manager(store=None)
        count = mgr.count_tokens([{"role": "user", "content": "hello"}])
        assert count > 0

    def test_count_tokens_empty(self):
        mgr = _make_manager(store=None)
        assert mgr.count_tokens([]) == 0


class TestStoreCreation:
    def test_creates_file_store(self, tmp_path):
        app_config = _make_app_config()
        config = ContextConfig(store_type="file", store_path=str(tmp_path / "sessions"))

        with (
            patch.object(ContextManager, "_create_memory_service", return_value=None),
            patch.object(ContextManager, "_create_summarizer", return_value=None),
            patch(
                "tank_backend.prompts.assembler.PromptAssembler.assemble",
                return_value="test",
            ),
        ):
            mgr = ContextManager(app_config=app_config, config=config)

        from tank_backend.context.file_store import FileSessionStore

        assert isinstance(mgr._store, FileSessionStore)

    def test_creates_sqlite_store(self, tmp_path):
        app_config = _make_app_config()
        config = ContextConfig(
            store_type="sqlite", store_path=str(tmp_path / "test.db")
        )

        with (
            patch.object(ContextManager, "_create_memory_service", return_value=None),
            patch.object(ContextManager, "_create_summarizer", return_value=None),
            patch(
                "tank_backend.prompts.assembler.PromptAssembler.assemble",
                return_value="test",
            ),
        ):
            mgr = ContextManager(app_config=app_config, config=config)

        from tank_backend.context.sqlite_store import SqliteSessionStore

        assert isinstance(mgr._store, SqliteSessionStore)
        mgr.close()


class TestProperties:
    def test_session_id_none_initially(self):
        mgr = _make_manager(store=None)
        assert mgr.session_id is None

    def test_session_id_after_new_session(self):
        mgr = _make_manager(store=None)
        sid = mgr.new_session()
        assert mgr.session_id == sid

    def test_prompt_assembler_exposed(self):
        mgr = _make_manager(store=None)
        assert mgr.prompt_assembler is not None
