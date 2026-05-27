"""Tests for /api/conversations/{id}/compactions endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tank_backend.api import deps
from tank_backend.context.compactions import CompactionRecord


def _make_record(
    *,
    id: str = "rec-1",
    conversation_id: str = "conv-1",
    parent_id: str | None = None,
    focus: str | None = None,
) -> CompactionRecord:
    return CompactionRecord(
        id=id,
        conversation_id=conversation_id,
        parent_id=parent_id,
        created_at=datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc),
        focus=focus,
        tokens_before=5000,
        tokens_after=1500,
        compacted_count=10,
        summary_text="summary of conversation",
        pre_compaction_messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
    )


@pytest.fixture
def mock_compaction_store():
    return MagicMock()


@pytest.fixture
def mock_conversation_store():
    return MagicMock()


@pytest.fixture
def client(mock_compaction_store, mock_conversation_store):
    from tank_backend.api.server import app

    prior_ctx = deps._deps["ctx"]
    mock_ctx = MagicMock()
    mock_ctx.compaction_store = mock_compaction_store
    mock_ctx.conversation_store = mock_conversation_store
    deps._deps["ctx"] = mock_ctx
    yield TestClient(app)
    deps._deps["ctx"] = prior_ctx


class TestListCompactions:
    def test_returns_records_newest_first(
        self, client, mock_compaction_store,
    ):
        records = [
            _make_record(id="new"),
            _make_record(id="old", parent_id="new"),
        ]
        mock_compaction_store.list_for_conversation.return_value = records

        response = client.get("/api/conversations/conv-1/compactions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "new"
        assert data[1]["id"] == "old"
        assert data[0]["pre_compaction_messages"] is None

    def test_include_messages_flag(
        self, client, mock_compaction_store,
    ):
        mock_compaction_store.list_for_conversation.return_value = [
            _make_record(),
        ]

        response = client.get(
            "/api/conversations/conv-1/compactions?include_messages=true"
        )

        assert response.status_code == 200
        data = response.json()
        assert data[0]["pre_compaction_messages"] is not None
        assert len(data[0]["pre_compaction_messages"]) == 2

    def test_empty_list(self, client, mock_compaction_store):
        mock_compaction_store.list_for_conversation.return_value = []

        response = client.get("/api/conversations/conv-1/compactions")

        assert response.status_code == 200
        assert response.json() == []


class TestRestoreCompaction:
    def test_restore_re_inflates_messages(
        self, client, mock_compaction_store, mock_conversation_store,
    ):
        record = _make_record()
        mock_compaction_store.get.return_value = record
        mock_compaction_store.delete_descendants.return_value = 1

        # Simulate a post-compaction conversation:
        # [system, summary_msg, tail_msg]
        conv = MagicMock()
        conv.messages = [
            {"role": "system", "content": "You are helpful."},
            {
                "role": "system",
                "content": "Previous conversation summary:\nsummary",
                "metadata": {"type": "compaction_summary"},
            },
            {"role": "user", "content": "latest question"},
        ]
        mock_conversation_store.load.return_value = conv

        response = client.post(
            "/api/conversations/conv-1/compactions/rec-1/restore"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["messages_restored"] == 2
        assert body["descendants_removed"] == 1
        assert body["conversation_id"] == "conv-1"
        assert body["restored_compaction_id"] == "rec-1"
        # The restored record's id must be the one passed to delete_descendants
        # — that's how the chain prune works.
        mock_compaction_store.delete_descendants.assert_called_once_with(
            "rec-1",
        )

        # Verify the conversation was saved with restored messages.
        mock_conversation_store.save.assert_called_once_with(conv)
        expected_messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "latest question"},
        ]
        assert conv.messages == expected_messages

    def test_restore_unknown_compaction_returns_404(
        self, client, mock_compaction_store,
    ):
        mock_compaction_store.get.return_value = None

        response = client.post(
            "/api/conversations/conv-1/compactions/missing/restore"
        )

        assert response.status_code == 404

    def test_restore_wrong_conversation_returns_404(
        self, client, mock_compaction_store,
    ):
        record = _make_record(conversation_id="other-conv")
        mock_compaction_store.get.return_value = record

        response = client.post(
            "/api/conversations/conv-1/compactions/rec-1/restore"
        )

        assert response.status_code == 404

    def test_restore_unknown_conversation_returns_404(
        self, client, mock_compaction_store, mock_conversation_store,
    ):
        record = _make_record()
        mock_compaction_store.get.return_value = record
        mock_conversation_store.load.return_value = None

        response = client.post(
            "/api/conversations/conv-1/compactions/rec-1/restore"
        )

        assert response.status_code == 404

    def test_restore_without_summary_msg_keeps_all_tail(
        self, client, mock_compaction_store, mock_conversation_store,
    ):
        record = _make_record()
        mock_compaction_store.get.return_value = record
        mock_compaction_store.delete_descendants.return_value = 1

        # No summary message — just system + tail.
        conv = MagicMock()
        conv.messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "tail msg"},
        ]
        mock_conversation_store.load.return_value = conv

        response = client.post(
            "/api/conversations/conv-1/compactions/rec-1/restore"
        )

        assert response.status_code == 200
        expected = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "tail msg"},
        ]
        assert conv.messages == expected


class TestRestoreEndToEnd:
    """Restore against a real CompactionStore + SqliteConversationStore.

    The mocked tests above verify call wiring; this one verifies that
    deleting descendants actually walks the parent chain and that the
    re-inflated conversation persists across a reload.
    """

    @pytest.fixture
    def real_db(self, tmp_path):
        from tank_backend.persistence import Database, run_migrations

        url = f"sqlite+pysqlite:///{tmp_path}/tank.db"
        run_migrations(url)
        db = Database(url)
        yield db
        db.dispose()

    @pytest.fixture
    def stores(self, real_db):
        from tank_backend.context.compaction_store import CompactionStore
        from tank_backend.context.sqlite_store import SqliteConversationStore

        return SqliteConversationStore(real_db), CompactionStore(real_db)

    @pytest.fixture
    def real_client(self, stores):
        from tank_backend.api.server import app

        conv_store, compaction_store = stores
        prior_ctx = deps._deps["ctx"]
        mock_ctx = MagicMock()
        mock_ctx.compaction_store = compaction_store
        mock_ctx.conversation_store = conv_store
        deps._deps["ctx"] = mock_ctx
        yield TestClient(app)
        deps._deps["ctx"] = prior_ctx

    def test_restore_chain_prunes_descendants(self, real_client, stores):
        """Build chain a → b → c, restore from a, expect b and c gone."""
        from tank_backend.context.conversation import ConversationData

        conv_store, compaction_store = stores

        # Seed conversation in post-compaction state
        conv = ConversationData(
            id="conv-x",
            start_time=datetime(2026, 5, 26, tzinfo=timezone.utc),
            pid=1,
            messages=[
                {"role": "system", "content": "system"},
                {
                    "role": "system",
                    "content": "Previous conversation summary:\nlatest",
                    "metadata": {"type": "compaction_summary"},
                },
                {"role": "user", "content": "tail"},
            ],
        )
        conv_store.save(conv)

        # Build a → b → c chain. Each ``parent_id`` points up the chain
        # toward the oldest record.
        for i, (rid, parent) in enumerate([("a", None), ("b", "a"), ("c", "b")]):
            compaction_store.save(CompactionRecord(
                id=rid,
                conversation_id="conv-x",
                parent_id=parent,
                created_at=datetime(2026, 5, 26, 10 + i, 0, tzinfo=timezone.utc),
                focus=None,
                tokens_before=1000,
                tokens_after=500,
                compacted_count=2,
                summary_text=f"summary-{rid}",
                pre_compaction_messages=[
                    {"role": "user", "content": f"orig-{rid}-1"},
                    {"role": "assistant", "content": f"orig-{rid}-2"},
                ],
            ))

        # Restore from the oldest (a). Should remove a + b + c.
        response = real_client.post(
            "/api/conversations/conv-x/compactions/a/restore"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["messages_restored"] == 2
        assert body["descendants_removed"] == 3

        # All three records gone.
        assert compaction_store.list_for_conversation("conv-x") == []

        # Conversation persisted with original messages re-inflated.
        reloaded = conv_store.load("conv-x")
        assert reloaded is not None
        contents = [m.get("content") for m in reloaded.messages]
        assert "orig-a-1" in contents
        assert "orig-a-2" in contents
        # The summary message is gone (replaced).
        assert not any(
            (m.get("metadata") or {}).get("type") == "compaction_summary"
            for m in reloaded.messages
        )

    def test_restore_middle_of_chain_prunes_only_self_and_below(
        self, real_client, stores,
    ):
        """Chain a → b → c. Restoring b should remove b and c, keep a."""
        from tank_backend.context.conversation import ConversationData

        conv_store, compaction_store = stores
        conv_store.save(ConversationData(
            id="conv-y",
            start_time=datetime(2026, 5, 26, tzinfo=timezone.utc),
            pid=1,
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "tail"},
            ],
        ))

        for i, (rid, parent) in enumerate([("a", None), ("b", "a"), ("c", "b")]):
            compaction_store.save(CompactionRecord(
                id=rid,
                conversation_id="conv-y",
                parent_id=parent,
                created_at=datetime(2026, 5, 26, 10 + i, 0, tzinfo=timezone.utc),
                focus=None,
                tokens_before=1000,
                tokens_after=500,
                compacted_count=1,
                summary_text=f"sum-{rid}",
                pre_compaction_messages=[
                    {"role": "user", "content": f"m-{rid}"},
                ],
            ))

        response = real_client.post(
            "/api/conversations/conv-y/compactions/b/restore"
        )

        assert response.status_code == 200
        assert response.json()["descendants_removed"] == 2

        remaining_ids = {
            r.id for r in compaction_store.list_for_conversation("conv-y")
        }
        assert remaining_ids == {"a"}
