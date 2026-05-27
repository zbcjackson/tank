"""Tests for /api/memory/consolidate endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tank_backend.api import deps
from tank_backend.config.models import ConsolidationConfig, PreferenceConfig
from tank_backend.memory.consolidator import ConsolidationReport


@pytest.fixture
def app_config(tmp_path):
    cfg = MagicMock()
    cfg.consolidation = ConsolidationConfig(enabled=True)
    cfg.preferences = PreferenceConfig(enabled=True, base_dir=str(tmp_path))
    cfg.memory = MagicMock(enabled=False)
    cfg.get_llm_profile.side_effect = KeyError("not configured in tests")
    return cfg


@pytest.fixture
def client(app_config):
    from tank_backend.api.server import app

    prior_ctx = deps._deps["ctx"]
    mock_ctx = MagicMock()
    mock_ctx.app_config = app_config
    mock_ctx.compaction_store = None
    mock_ctx.conversation_store = None
    deps._deps["ctx"] = mock_ctx

    yield TestClient(app)
    deps._deps["ctx"] = prior_ctx


def _report(user: str, promoted: list[str] | None = None) -> ConsolidationReport:
    now = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    return ConsolidationReport(
        started_at=now,
        finished_at=now,
        user=user,
        candidates_scanned=5,
        promoted=promoted or [],
    )


class TestConsolidateAPI:
    def test_disabled_returns_503(self, client, app_config):
        app_config.consolidation = ConsolidationConfig(enabled=False)

        response = client.post("/api/memory/consolidate", json={})
        assert response.status_code == 503

    def test_consolidator_unavailable_returns_503(self, client):
        with patch(
            "tank_backend.memory.consolidator.build_consolidator",
            return_value=None,
        ):
            response = client.post("/api/memory/consolidate", json={})
            assert response.status_code == 503

    def test_specific_user_runs_once(self, client):
        consolidator = MagicMock()
        consolidator.run = AsyncMock(
            return_value=_report("jackson", promoted=["fact"]),
        )
        with patch(
            "tank_backend.memory.consolidator.build_consolidator",
            return_value=consolidator,
        ):
            response = client.post(
                "/api/memory/consolidate",
                json={"user_id": "jackson"},
            )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["user"] == "jackson"
        assert body[0]["promoted"] == ["fact"]
        consolidator.run.assert_awaited_once_with("jackson", force=True)

    def test_no_users_returns_empty_list(self, client):
        # tmp_path/users doesn't exist → no known users.
        consolidator = MagicMock()
        consolidator.run = AsyncMock()
        with patch(
            "tank_backend.memory.consolidator.build_consolidator",
            return_value=consolidator,
        ):
            response = client.post("/api/memory/consolidate", json={})

        assert response.status_code == 200
        assert response.json() == []
        consolidator.run.assert_not_awaited()

    def test_force_false_propagates(self, client):
        consolidator = MagicMock()
        consolidator.run = AsyncMock(return_value=_report("jackson"))
        with patch(
            "tank_backend.memory.consolidator.build_consolidator",
            return_value=consolidator,
        ):
            response = client.post(
                "/api/memory/consolidate",
                json={"user_id": "jackson", "force": False},
            )

        assert response.status_code == 200
        consolidator.run.assert_awaited_once_with("jackson", force=False)
