"""Tests for /api/memory endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tank_backend.api import deps


@dataclass(frozen=True)
class _PrefsCfg:
    enabled: bool = True
    max_entries: int = 20
    auto_learn: bool = True
    base_dir: str = ""


@dataclass(frozen=True)
class _MemCfg:
    enabled: bool = False
    db_path: str = "/tmp/mem"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    search_limit: int = 5


@pytest.fixture
def temp_prefs(tmp_path: Path):
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "preferences.md").write_text(
        "- Prefers Celsius [explicit, 2026-04-21]\n"
        "- Lives in Tokyo [pinned, 2026-04-21]\n"
        "- Likes hiking [inferred, 2026-04-21]\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def app_ctx_with_prefs(temp_prefs: Path):
    ctx = MagicMock()
    ctx.app_config.preferences = _PrefsCfg(
        enabled=True,
        max_entries=20,
        base_dir=str(temp_prefs),
    )
    ctx.app_config.memory = _MemCfg(enabled=False)
    return ctx


@pytest.fixture
def client(app_ctx_with_prefs):
    from tank_backend.api.server import app

    prior = deps._deps["ctx"]
    deps._deps["ctx"] = app_ctx_with_prefs
    yield TestClient(app)
    deps._deps["ctx"] = prior


class TestMemoryAPI:
    def test_get_user_memory_returns_pinned_and_learned(self, client):
        response = client.get("/api/memory/alice")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "alice"
        assert data["pinned"] == ["Lives in Tokyo"]
        assert sorted(data["learned"]) == sorted(["Prefers Celsius", "Likes hiking"])
        assert data["facts"] == []

    def test_get_user_memory_unknown_user_returns_empty(self, client):
        response = client.get("/api/memory/nobody")

        assert response.status_code == 200
        data = response.json()
        assert data == {
            "user_id": "nobody",
            "pinned": [],
            "learned": [],
            "facts": [],
        }

    def test_facts_come_from_memory_service(
        self, app_ctx_with_prefs, temp_prefs: Path,
    ):
        """When memory is enabled, ``facts`` is populated from MemoryService."""
        from tank_backend.api.server import app

        app_ctx_with_prefs.app_config.memory = _MemCfg(
            enabled=True,
            db_path=str(temp_prefs / "mem"),
            llm_api_key="sk-test",
        )
        app_ctx_with_prefs.app_config.get_llm_profile = MagicMock(
            return_value=MagicMock(api_key="sk-test", base_url="http://x"),
        )

        mock_service = MagicMock()
        mock_service.get_all = AsyncMock(
            return_value=["Likes coffee", "uses uv not pip"],
        )

        prior = deps._deps["ctx"]
        deps._deps["ctx"] = app_ctx_with_prefs
        try:
            with patch(
                "tank_backend.api.memory.MemoryService",
                return_value=mock_service,
            ):
                tc = TestClient(app)
                response = tc.get("/api/memory/alice")
        finally:
            deps._deps["ctx"] = prior

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "alice"
        assert data["pinned"] == ["Lives in Tokyo"]
        assert sorted(data["learned"]) == sorted(["Prefers Celsius", "Likes hiking"])
        assert data["facts"] == ["Likes coffee", "uses uv not pip"]
        mock_service.get_all.assert_awaited_once_with("alice")

    def test_memory_disabled_returns_empty_facts(self, client):
        """When mem0 is disabled, the response still 200s with ``facts: []``."""
        response = client.get("/api/memory/alice")

        assert response.status_code == 200
        data = response.json()
        assert data["facts"] == []

    def test_get_user_memory_disabled_store_returns_503(self, tmp_path):
        ctx = MagicMock()
        ctx.app_config.preferences = _PrefsCfg(enabled=False, base_dir=str(tmp_path))
        ctx.app_config.memory = _MemCfg(enabled=False)
        prior = deps._deps["ctx"]
        deps._deps["ctx"] = ctx
        try:
            from tank_backend.api.server import app

            client = TestClient(app)
            response = client.get("/api/memory/alice")
            assert response.status_code == 503
        finally:
            deps._deps["ctx"] = prior

    def test_guest_user_returns_empty(self, client):
        response = client.get("/api/memory/Unknown")

        assert response.status_code == 200
        data = response.json()
        assert data == {
            "user_id": "Unknown",
            "pinned": [],
            "learned": [],
            "facts": [],
        }
