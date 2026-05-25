"""Tests for /api/context/usage endpoint."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tank_backend.api import deps
from tank_backend.context.manager import UsageSnapshot


def _snapshot(
    *,
    tokens_used: int = 1000,
    budget: int = 8000,
    context_window: int = 32000,
    fill_pct: float = 0.125,
    last_compaction_at: str | None = None,
    ineffective_count: int = 0,
    compaction_passes: int = 0,
    conversation_id: str | None = "conv-1",
) -> UsageSnapshot:
    return UsageSnapshot(
        tokens_used=tokens_used,
        budget=budget,
        context_window=context_window,
        fill_pct=fill_pct,
        last_compaction_at=last_compaction_at,
        ineffective_count=ineffective_count,
        compaction_passes=compaction_passes,
        conversation_id=conversation_id,
    )


def _assistant_with_snapshot(snapshot: UsageSnapshot) -> MagicMock:
    assistant = MagicMock()
    assistant.brain._context.usage_snapshot.return_value = snapshot
    return assistant


@pytest.fixture
def mock_connection_manager():
    return MagicMock()


@pytest.fixture
def client(mock_connection_manager):
    from tank_backend.api.server import app

    prior = deps._mgr["v"]
    deps._mgr["v"] = mock_connection_manager
    yield TestClient(app)
    deps._mgr["v"] = prior


class TestUsageAPI:
    def test_get_session_usage_returns_snapshot_fields(self, client, mock_connection_manager):
        snapshot = _snapshot(
            tokens_used=1234,
            budget=8000,
            context_window=128000,
            fill_pct=0.154,
            last_compaction_at="2026-05-24T12:00:00+00:00",
            ineffective_count=1,
            compaction_passes=2,
            conversation_id="abc",
        )
        mock_connection_manager.get_assistant.return_value = _assistant_with_snapshot(snapshot)

        response = client.get("/api/context/usage/session-1")

        assert response.status_code == 200
        data = response.json()
        assert data == {
            "session_id": "session-1",
            "conversation_id": "abc",
            "tokens_used": 1234,
            "budget": 8000,
            "context_window": 128000,
            "fill_pct": 0.154,
            "last_compaction_at": "2026-05-24T12:00:00+00:00",
            "ineffective_count": 1,
            "compaction_passes": 2,
        }

    def test_get_session_usage_not_found(self, client, mock_connection_manager):
        mock_connection_manager.get_assistant.return_value = None

        response = client.get("/api/context/usage/missing")

        assert response.status_code == 404

    def test_get_all_usage_lists_each_session(self, client, mock_connection_manager):
        snap_a = _snapshot(tokens_used=100, conversation_id="a")
        snap_b = _snapshot(tokens_used=200, conversation_id="b")
        mock_connection_manager.iter_sessions.return_value = [
            ("s1", _assistant_with_snapshot(snap_a)),
            ("s2", _assistant_with_snapshot(snap_b)),
        ]

        response = client.get("/api/context/usage")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        sessions = {row["session_id"]: row for row in data}
        assert sessions["s1"]["tokens_used"] == 100
        assert sessions["s1"]["conversation_id"] == "a"
        assert sessions["s2"]["tokens_used"] == 200
        assert sessions["s2"]["conversation_id"] == "b"

    def test_get_all_usage_empty(self, client, mock_connection_manager):
        mock_connection_manager.iter_sessions.return_value = []

        response = client.get("/api/context/usage")

        assert response.status_code == 200
        assert response.json() == []


class TestCompactAPI:
    def _make_assistant(
        self, tokens_before: int, tokens_after: int
    ) -> MagicMock:
        ctx = MagicMock()
        ctx.count_tokens.side_effect = [tokens_before, tokens_after]
        ctx.compact = AsyncMock()
        assistant = MagicMock()
        assistant.brain._context = ctx
        return assistant

    def test_compact_with_focus_invokes_manager(
        self, client, mock_connection_manager
    ):
        assistant = self._make_assistant(8000, 2000)
        mock_connection_manager.get_assistant.return_value = assistant

        response = client.post(
            "/api/context/compact/session-1",
            json={"focus": "API design"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body == {
            "session_id": "session-1",
            "tokens_before": 8000,
            "tokens_after": 2000,
            "focus": "API design",
        }
        assistant.brain._context.compact.assert_awaited_once_with(focus="API design")

    def test_compact_without_focus_passes_none(
        self, client, mock_connection_manager
    ):
        assistant = self._make_assistant(500, 500)
        mock_connection_manager.get_assistant.return_value = assistant

        response = client.post("/api/context/compact/session-1", json={})

        assert response.status_code == 200
        body = response.json()
        assert body["focus"] is None
        assistant.brain._context.compact.assert_awaited_once_with(focus=None)

    def test_compact_empty_body_passes_none(
        self, client, mock_connection_manager
    ):
        assistant = self._make_assistant(500, 500)
        mock_connection_manager.get_assistant.return_value = assistant

        response = client.post("/api/context/compact/session-1")

        assert response.status_code == 200
        assert response.json()["focus"] is None
        assistant.brain._context.compact.assert_awaited_once_with(focus=None)

    def test_compact_unknown_session_returns_404(
        self, client, mock_connection_manager
    ):
        mock_connection_manager.get_assistant.return_value = None

        response = client.post(
            "/api/context/compact/missing", json={"focus": "x"}
        )

        assert response.status_code == 404
