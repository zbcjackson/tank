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
