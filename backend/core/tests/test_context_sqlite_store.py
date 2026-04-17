"""Tests for context.sqlite_store — SqliteConversationStore."""

from datetime import datetime, timezone

import pytest

from tank_backend.context.conversation import ConversationData
from tank_backend.context.sqlite_store import SqliteConversationStore


@pytest.fixture
def store(tmp_path):
    s = SqliteConversationStore(tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def sample_conversation():
    return ConversationData(
        id="abc123",
        start_time=datetime(2026, 4, 14, 10, 30, 0, tzinfo=timezone.utc),
        pid=12345,
        messages=[
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ],
    )


class TestSqliteConversationStore:
    def test_save_and_load_roundtrip(self, store, sample_conversation):
        store.save(sample_conversation)
        loaded = store.load("abc123")
        assert loaded is not None
        assert loaded.id == "abc123"
        assert loaded.messages == sample_conversation.messages

    def test_load_nonexistent_returns_none(self, store):
        assert store.load("nonexistent") is None

    def test_save_overwrites_existing(self, store, sample_conversation):
        store.save(sample_conversation)
        sample_conversation.messages.append({"role": "assistant", "content": "Hi!"})
        store.save(sample_conversation)
        loaded = store.load("abc123")
        assert len(loaded.messages) == 3

    def test_delete_removes_conversation(self, store, sample_conversation):
        store.save(sample_conversation)
        store.delete("abc123")
        assert store.load("abc123") is None

    def test_list_conversations(self, store):
        s1 = ConversationData(
            id="a",
            start_time=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
            pid=1,
            messages=[{"role": "system", "content": "a"}],
        )
        s2 = ConversationData(
            id="b",
            start_time=datetime(2026, 4, 14, 11, 0, 0, tzinfo=timezone.utc),
            pid=2,
            messages=[{"role": "system", "content": "b"}],
        )
        store.save(s1)
        store.save(s2)
        conversations = store.list_conversations()
        ids = [s.id for s in conversations]
        assert "a" in ids
        assert "b" in ids

    def test_find_latest(self, store):
        s1 = ConversationData(
            id="old",
            start_time=datetime(2026, 4, 13, 10, 0, 0, tzinfo=timezone.utc),
            pid=1,
            messages=[{"role": "system", "content": "a"}],
        )
        s2 = ConversationData(
            id="new",
            start_time=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
            pid=2,
            messages=[{"role": "system", "content": "b"}],
        )
        store.save(s1)
        store.save(s2)
        latest = store.find_latest()
        assert latest is not None
        assert latest.id == "new"

    def test_find_latest_empty(self, store):
        assert store.find_latest() is None

    def test_close_safe_multiple_times(self, tmp_path):
        s = SqliteConversationStore(tmp_path / "test2.db")
        s.close()
        s.close()  # should not raise
