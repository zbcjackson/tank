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
    from tank_backend.llm.profile import LLMProfile

    cfg = MagicMock()
    cfg.consolidation = ConsolidationConfig(enabled=True)
    cfg.preferences = PreferenceConfig(enabled=True, base_dir=str(tmp_path))
    cfg.memory = MagicMock(enabled=False)
    cfg.get_llm_profile.return_value = LLMProfile(
        name="default",
        api_key="test",
        model="gpt-4o",
        base_url="http://example.test",
    )
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

    def test_bulk_run_iterates_known_users(self, client, tmp_path):
        # Seed two user dirs with preferences.md so _list_known_users
        # actually returns them.
        for name in ("jackson", "alice"):
            (tmp_path / "users" / name).mkdir(parents=True)
            (tmp_path / "users" / name / "preferences.md").write_text("- fact\n")

        consolidator = MagicMock()
        consolidator.run = AsyncMock(side_effect=lambda u, force: _report(u))
        with patch(
            "tank_backend.memory.consolidator.build_consolidator",
            return_value=consolidator,
        ):
            response = client.post("/api/memory/consolidate", json={})

        assert response.status_code == 200
        body = response.json()
        users_returned = sorted(r["user"] for r in body)
        assert users_returned == ["alice", "jackson"]
        assert consolidator.run.await_count == 2


class TestProfileFallback:
    """build_consolidator() relies on AppConfig.get_llm_profile() to fall
    back to the ``default`` profile when the configured one is missing.
    This test verifies the integration: when ``get_llm_profile`` returns
    the default profile (its real fallback behaviour), build_consolidator
    constructs the LLM with it.
    """

    def test_uses_profile_returned_by_get_llm_profile(self, tmp_path):
        from tank_backend.config.models import (
            ConsolidationConfig,
            MemoryConfig,
            PreferenceConfig,
        )
        from tank_backend.memory.consolidator import build_consolidator

        default_profile = MagicMock(
            api_key="k", base_url="https://example", model="gpt-x",
            temperature=0.2, max_tokens=4000,
            extra_headers={}, extra_body=None, stream_options=False,
        )

        cfg = MagicMock()
        cfg.consolidation = ConsolidationConfig(
            enabled=True, llm_profile="consolidation",
        )
        cfg.preferences = PreferenceConfig(
            enabled=True, base_dir=str(tmp_path),
        )
        cfg.memory = MemoryConfig(enabled=False)
        # Real AppConfig.get_llm_profile falls back to default for any
        # missing name; the mock mirrors that.
        cfg.get_llm_profile.return_value = default_profile

        with patch(
            "tank_backend.llm.profile.create_llm_from_profile",
        ) as mock_create:
            mock_create.return_value = MagicMock()
            consolidator = build_consolidator(cfg)

        assert consolidator is not None
        mock_create.assert_called_once_with(default_profile)
        cfg.get_llm_profile.assert_called_with("consolidation")
