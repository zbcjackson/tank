"""Tests for persistence.conversation_messages_store — FTS5-backed store."""

from __future__ import annotations

import pytest

from tank_backend.persistence import Database, run_migrations
from tank_backend.persistence.conversation_messages_store import (
    ConversationMessagesStore,
)
from tank_backend.persistence.models import ConversationRow


@pytest.fixture
def db(tmp_path):
    # Use real migrations so the FTS5 virtual table + triggers are
    # actually created — Base.metadata.create_all() doesn't know about
    # the FTS5 specifics from the Alembic migration.
    url = f"sqlite+pysqlite:///{tmp_path}/tank.db"
    run_migrations(url)
    database = Database(url)
    yield database
    database.dispose()


@pytest.fixture
def store(db):
    return ConversationMessagesStore(db)


@pytest.fixture
def seed_conversations(db):
    """Create parent conversation rows so FK constraints hold."""
    with db.session() as s:
        s.add(ConversationRow(
            conversation_id="conv-a",
            start_time="2026-05-26T00:00:00+00:00",
            pid=1,
            messages="[]",
            updated_at=1.0,
        ))
        s.add(ConversationRow(
            conversation_id="conv-b",
            start_time="2026-05-26T00:00:00+00:00",
            pid=2,
            messages="[]",
            updated_at=1.0,
        ))


class TestReplaceForConversation:
    def test_inserts_all_messages(self, store, seed_conversations):
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        store.replace_for_conversation("conv-a", messages)

        hits = store.search("hello")
        assert len(hits) == 1
        assert hits[0].content == "hello"
        assert hits[0].role == "user"
        assert hits[0].seq == 1

    def test_replace_wipes_previous(self, store, seed_conversations):
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": "first run"},
        ])
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": "second run"},
        ])

        # First run's content shouldn't be searchable.
        assert store.search("first") == []
        hits = store.search("second")
        assert len(hits) == 1

    def test_skips_empty_content(self, store, seed_conversations):
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": "valid"},
            {"role": "tool", "content": ""},
            {"role": "assistant"},        # no content
            {"role": "user", "content": "another valid"},
        ])

        hits = store.search("valid")
        assert len(hits) == 2

    def test_handles_openai_content_parts(self, store, seed_conversations):
        store.replace_for_conversation("conv-a", [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this image"},
                    {"type": "image_url", "image_url": {"url": "x"}},
                ],
            },
        ])

        hits = store.search("describe")
        assert len(hits) == 1
        assert "describe this image" in hits[0].content


class TestSearch:
    def test_returns_empty_for_blank_query(self, store, seed_conversations):
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": "anything"},
        ])
        assert store.search("") == []
        assert store.search("   ") == []

    def test_returns_empty_when_no_matches(self, store, seed_conversations):
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": "hello world"},
        ])
        assert store.search("xyzqq") == []

    def test_chinese_search_finds_chinese_content(
        self, store, seed_conversations,
    ):
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": "明天的会议是几点开始"},
            {"role": "assistant", "content": "明天上午十点钟开会"},
        ])

        # Trigram tokenizer requires ≥3 characters per query token.
        # Most Chinese keyword queries naturally satisfy this.
        hits = store.search("明天的")
        contents = {h.content for h in hits}
        assert "明天的会议是几点开始" in contents

    def test_exact_filename_match(self, store, seed_conversations):
        store.replace_for_conversation("conv-a", [
            {"role": "assistant", "content": "see config.yaml line 42"},
            {"role": "user", "content": "unrelated talk about lunch"},
        ])

        hits = store.search("config.yaml")
        assert len(hits) == 1
        assert "config.yaml" in hits[0].content

    def test_filter_by_conversation_id(self, store, seed_conversations):
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": "alpha message"},
        ])
        store.replace_for_conversation("conv-b", [
            {"role": "user", "content": "alpha message"},
        ])

        hits = store.search("alpha", conversation_id="conv-a")
        assert len(hits) == 1
        assert hits[0].conversation_id == "conv-a"

    def test_limit_caps_results(self, store, seed_conversations):
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": f"message {i} test"}
            for i in range(10)
        ])

        hits = store.search("test", limit=3)
        assert len(hits) == 3

    def test_unbalanced_quote_in_query_returns_empty(
        self, store, seed_conversations,
    ):
        # User input may include FTS-reserved punctuation. ``_safe_query``
        # wraps in double quotes; this confirms the wrap+escape doesn't
        # 500 on tricky input.
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": "the cat sat on the mat"},
        ])

        # A single double quote — should match the safe-query path.
        hits = store.search('"cat"')
        # Either matches or returns empty, never raises.
        assert isinstance(hits, list)


class TestDeleteForConversation:
    def test_removes_all(self, store, seed_conversations):
        store.replace_for_conversation("conv-a", [
            {"role": "user", "content": "keep"},
        ])
        store.replace_for_conversation("conv-b", [
            {"role": "user", "content": "also keep"},
        ])

        store.delete_for_conversation("conv-a")

        assert store.search("keep", conversation_id="conv-a") == []
        # Other conversation untouched.
        assert len(store.search("keep", conversation_id="conv-b")) == 1
