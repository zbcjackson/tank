"""Tests for context.compaction_store — CompactionStore."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tank_backend.context.compaction_store import CompactionStore
from tank_backend.context.compactions import CompactionRecord
from tank_backend.context.conversation import ConversationData
from tank_backend.context.sqlite_store import SqliteConversationStore
from tank_backend.persistence import Base, Database


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(database.engine)
    yield database
    database.dispose()


@pytest.fixture
def conversation_store(db):
    s = SqliteConversationStore(db)
    # Compactions FK conversations, so we need a parent row.
    s.save(ConversationData(
        id="conv-1",
        start_time=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        pid=1,
        messages=[{"role": "system", "content": "hi"}],
    ))
    yield s


@pytest.fixture
def store(db, conversation_store):
    return CompactionStore(db)


def _make_record(
    *,
    id: str = "rec-1",
    conversation_id: str = "conv-1",
    parent_id: str | None = None,
    created_at: datetime | None = None,
    focus: str | None = None,
    tokens_before: int = 5000,
    tokens_after: int = 1500,
    compacted_count: int = 10,
    summary_text: str = "summary",
    pre_compaction_messages: list[dict] | None = None,
) -> CompactionRecord:
    return CompactionRecord(
        id=id,
        conversation_id=conversation_id,
        parent_id=parent_id,
        created_at=created_at or datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        focus=focus,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        compacted_count=compacted_count,
        summary_text=summary_text,
        pre_compaction_messages=pre_compaction_messages or [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
    )


class TestCompactionStore:
    def test_save_and_get_roundtrip(self, store):
        record = _make_record(focus="API design")
        store.save(record)

        loaded = store.get("rec-1")
        assert loaded is not None
        assert loaded.id == "rec-1"
        assert loaded.conversation_id == "conv-1"
        assert loaded.focus == "API design"
        assert loaded.tokens_before == 5000
        assert loaded.tokens_after == 1500
        assert loaded.compacted_count == 10
        assert loaded.summary_text == "summary"
        assert loaded.pre_compaction_messages == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        assert loaded.created_at == record.created_at

    def test_get_nonexistent_returns_none(self, store):
        assert store.get("does-not-exist") is None

    def test_list_for_conversation_orders_newest_first(self, store):
        store.save(_make_record(
            id="old",
            created_at=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        ))
        store.save(_make_record(
            id="new",
            created_at=datetime(2026, 5, 26, 11, 0, 0, tzinfo=timezone.utc),
        ))

        records = store.list_for_conversation("conv-1")
        assert [r.id for r in records] == ["new", "old"]

    def test_list_for_conversation_empty(self, store):
        assert store.list_for_conversation("conv-1") == []

    def test_latest_for_conversation(self, store):
        store.save(_make_record(
            id="old",
            created_at=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        ))
        store.save(_make_record(
            id="new",
            created_at=datetime(2026, 5, 26, 11, 0, 0, tzinfo=timezone.utc),
        ))

        latest = store.latest_for_conversation("conv-1")
        assert latest is not None
        assert latest.id == "new"

    def test_latest_for_conversation_empty(self, store):
        assert store.latest_for_conversation("conv-1") is None

    def test_delete_descendants_removes_chain(self, store):
        # Build a chain: a -> b -> c (parent_id back-pointers)
        store.save(_make_record(id="a", parent_id=None))
        store.save(_make_record(id="b", parent_id="a"))
        store.save(_make_record(id="c", parent_id="b"))
        store.save(_make_record(id="x", parent_id=None))   # unrelated chain

        removed = store.delete_descendants("a")
        assert removed == 3

        assert store.get("a") is None
        assert store.get("b") is None
        assert store.get("c") is None
        assert store.get("x") is not None

    def test_delete_descendants_only_subtree(self, store):
        # Build branching chain: a -> b, a -> c
        store.save(_make_record(id="a", parent_id=None))
        store.save(_make_record(id="b", parent_id="a"))
        store.save(_make_record(id="c", parent_id="a"))

        removed = store.delete_descendants("b")
        assert removed == 1
        assert store.get("a") is not None
        assert store.get("b") is None
        assert store.get("c") is not None

    def test_delete_descendants_unknown_id_returns_zero(self, store):
        removed = store.delete_descendants("no-such-id")
        assert removed == 0

    def test_delete_for_conversation_removes_all(self, store, db):
        # Create another conversation row so we can show isolation
        from tank_backend.context.sqlite_store import SqliteConversationStore
        SqliteConversationStore(db).save(ConversationData(
            id="conv-2",
            start_time=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
            pid=2,
            messages=[{"role": "system", "content": "hi"}],
        ))

        store.save(_make_record(id="r1", conversation_id="conv-1"))
        store.save(_make_record(id="r2", conversation_id="conv-1"))
        store.save(_make_record(id="r3", conversation_id="conv-2"))

        store.delete_for_conversation("conv-1")

        assert store.list_for_conversation("conv-1") == []
        assert len(store.list_for_conversation("conv-2")) == 1

    def test_save_preserves_unicode_in_messages(self, store):
        record = _make_record(pre_compaction_messages=[
            {"role": "user", "content": "你好,世界"},
            {"role": "assistant", "content": "Hello, 世界"},
        ])
        store.save(record)

        loaded = store.get("rec-1")
        assert loaded is not None
        assert loaded.pre_compaction_messages[0]["content"] == "你好,世界"
        assert loaded.pre_compaction_messages[1]["content"] == "Hello, 世界"

    def test_created_at_roundtrip_preserves_seconds(self, store):
        # Use a timestamp with a known second precision; SQLite's REAL
        # will preserve microseconds well enough.
        ts = datetime(2026, 5, 26, 10, 30, 45, 123456, tzinfo=timezone.utc)
        store.save(_make_record(id="precise", created_at=ts))

        loaded = store.get("precise")
        assert loaded is not None
        # Roundtrip via float timestamp loses sub-microsecond precision,
        # but seconds and microseconds should match.
        assert abs((loaded.created_at - ts).total_seconds()) < 0.001
