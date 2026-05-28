"""Tests for ``TitleGenerator`` — LLM titling + persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from tank_backend.context.conversation import ConversationData
from tank_backend.context.sqlite_store import SqliteConversationStore
from tank_backend.context.title_generator import (
    TitleGenerator,
    _clean_title,
    _extract_first_exchange,
)
from tank_backend.persistence import Base, Database


@pytest.fixture
def store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    s = SqliteConversationStore(db)
    yield s
    s.close()
    db.dispose()


def _conv(id_: str, messages: list[dict]) -> ConversationData:
    return ConversationData(
        id=id_,
        start_time=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
        pid=1,
        messages=messages,
    )


class TestExtractFirstExchange:
    def test_finds_first_user_and_assistant_pair(self):
        user, assistant = _extract_first_exchange([
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            {"role": "user", "content": "ignored second turn"},
        ])
        assert user == "hello"
        assert assistant == "hi there"

    def test_empty_when_no_user_message(self):
        user, assistant = _extract_first_exchange([
            {"role": "system", "content": "be helpful"},
        ])
        assert user == ""
        assert assistant == ""

    def test_handles_parts_list_content(self):
        user, _ = _extract_first_exchange([
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        ])
        assert user == "hi"

    def test_only_user_no_assistant_yet(self):
        user, assistant = _extract_first_exchange([
            {"role": "user", "content": "hello"},
        ])
        assert user == "hello"
        assert assistant == ""


class TestCleanTitle:
    def test_strips_whitespace(self):
        assert _clean_title("  Trip planning  ") == "Trip planning"

    def test_removes_surrounding_double_quotes(self):
        assert _clean_title('"Trip planning"') == "Trip planning"

    def test_removes_surrounding_curly_quotes(self):
        assert _clean_title("“Trip planning”") == "Trip planning"

    def test_strips_title_prefix(self):
        assert _clean_title("Title: Trip planning") == "Trip planning"

    def test_caps_at_eighty_chars(self):
        long = "x" * 200
        assert len(_clean_title(long)) == 80

    def test_collapses_internal_newlines(self):
        assert _clean_title("Trip\nplanning") == "Trip planning"


class TestTitleGenerator:
    async def test_generate_persists_title(self, store):
        store.save(_conv("c1", [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "Plan a Kyoto trip"},
            {"role": "assistant", "content": "Sure! How many days?"},
        ]))
        llm = AsyncMock()
        llm.complete.return_value = "Kyoto trip planning"

        gen = TitleGenerator(llm=llm, store=store)
        title = await gen.generate("c1")

        assert title == "Kyoto trip planning"
        assert store.load("c1").title == "Kyoto trip planning"

        # Prompt construction: both sides of the first exchange surface
        prompt = llm.complete.call_args.kwargs["messages"][1]["content"]
        assert "Plan a Kyoto trip" in prompt
        assert "Sure! How many days?" in prompt
        # And we asked for short output
        assert llm.complete.call_args.kwargs["max_tokens"] <= 64

    async def test_generate_returns_none_when_conversation_missing(self, store):
        llm = AsyncMock()
        gen = TitleGenerator(llm=llm, store=store)
        assert await gen.generate("does-not-exist") is None
        llm.complete.assert_not_called()

    async def test_generate_returns_none_when_llm_raises(self, store):
        store.save(_conv("c2", [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]))
        llm = AsyncMock()
        llm.complete.side_effect = RuntimeError("boom")

        gen = TitleGenerator(llm=llm, store=store)
        assert await gen.generate("c2") is None
        assert store.load("c2").title is None

    async def test_generate_strips_quotes_in_response(self, store):
        store.save(_conv("c3", [
            {"role": "user", "content": "x"},
            {"role": "assistant", "content": "y"},
        ]))
        llm = AsyncMock()
        llm.complete.return_value = '  "Quoted title"  '

        gen = TitleGenerator(llm=llm, store=store)
        title = await gen.generate("c3")
        assert title == "Quoted title"

    async def test_generate_skips_when_no_user_message(self, store):
        store.save(_conv("c4", [
            {"role": "system", "content": "be helpful"},
        ]))
        llm = AsyncMock()
        gen = TitleGenerator(llm=llm, store=store)
        assert await gen.generate("c4") is None
        llm.complete.assert_not_called()
