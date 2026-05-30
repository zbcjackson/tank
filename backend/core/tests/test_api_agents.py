"""Tests for /api/agents endpoints (Phase 2 step 6).

Pin the JSON shape returned to the web UI's "running tasks" panel
so frontend can rely on stable keys. The store fixture spins up a
real WorkerStore on a temp SQLite so endpoint behaviour is exercised
end-to-end against the same data layer the supervisor writes through.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tank_backend.agents.store import WorkerStore
from tank_backend.api import deps
from tank_backend.persistence import Base, Database


@pytest.fixture
def store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    yield WorkerStore(db)
    db.dispose()


@pytest.fixture
def client(store):
    """Test client with the worker store wired into AppContext."""
    from tank_backend.api.server import app

    fake_ctx = MagicMock()
    fake_ctx.worker_store = store
    prior_ctx = deps._deps.get("ctx")
    prior_mgr = deps._mgr.get("v")
    deps._deps["ctx"] = fake_ctx
    deps._mgr["v"] = MagicMock()
    yield TestClient(app)
    deps._deps["ctx"] = prior_ctx
    deps._mgr["v"] = prior_mgr


class TestListAgents:
    def test_lists_active_workers_only_by_default(self, client, store):
        store.create(task_id="t_run", agent_def="coder", prompt="x", description="A")
        store.create(task_id="t_done", agent_def="coder", prompt="y")
        store.finish("t_done", status="completed", output="o")

        resp = client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        ids = [r["task_id"] for r in data]
        assert ids == ["t_run"]
        # ``output`` is elided in list view (per _run_to_dict include_output=False).
        assert "output" not in data[0]
        assert data[0]["agent_def"] == "coder"
        assert data[0]["status"] == "running"

    def test_filter_by_conversation_returns_terminal_too(self, client, store):
        store.create(
            task_id="t_done",
            agent_def="coder",
            prompt="x",
            description="research",
            originating_conversation_id="conv_a",
        )
        store.finish("t_done", status="completed", output="o")
        store.create(
            task_id="t_run",
            agent_def="coder",
            prompt="x",
            originating_conversation_id="conv_a",
        )
        # A worker on a different conversation must not leak through.
        store.create(
            task_id="t_other",
            agent_def="coder",
            prompt="x",
            originating_conversation_id="conv_b",
        )

        resp = client.get(
            "/api/agents",
            params={"conversation_id": "conv_a", "include_terminal": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = sorted(r["task_id"] for r in data)
        assert ids == ["t_done", "t_run"]


class TestGetAgent:
    def test_returns_full_run_for_existing_task(self, client, store):
        store.create(
            task_id="t_done",
            agent_def="coder",
            prompt="x",
            description="research",
        )
        store.finish("t_done", status="completed", output="big result")

        resp = client.get("/api/agents/t_done")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "t_done"
        assert data["status"] == "completed"
        assert data["output"] == "big result"
        assert data["error"] is None

    def test_unknown_task_id_returns_404(self, client):
        resp = client.get("/api/agents/t_missing")
        assert resp.status_code == 404
