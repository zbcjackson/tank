"""Tests for Channel REST API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tank_backend.channels.store import ChannelStore
from tank_backend.context.conversation import ConversationData
from tank_backend.context.store import ConversationStore


class _MemoryConvStore(ConversationStore):
    """In-memory ConversationStore for tests."""

    def __init__(self) -> None:
        self._data: dict[str, ConversationData] = {}

    def save(self, conversation: ConversationData) -> None:
        self._data[conversation.id] = conversation

    def load(self, conversation_id: str) -> ConversationData | None:
        return self._data.get(conversation_id)

    def list_conversations(self):
        return []

    def delete(self, conversation_id: str) -> None:
        self._data.pop(conversation_id, None)

    def find_latest(self) -> ConversationData | None:
        return None


@pytest.fixture()
def client(tmp_path: Path):
    """Create a test client with injected channel and conversation stores."""
    from tank_backend.api import deps
    from tank_backend.api.server import app
    from tank_backend.config.context import AppContext

    channel_store = ChannelStore(tmp_path / "test_channels.db")
    conv_store = _MemoryConvStore()

    ctx = AppContext(
        app_config=deps.app_context().app_config,
        channel_store=channel_store,
        conversation_store=conv_store,
    )
    deps.init(ctx, deps.connection_manager())

    tc = TestClient(app, raise_server_exceptions=False)
    tc._channel_store = channel_store  # type: ignore[attr-defined]
    tc._conv_store = conv_store  # type: ignore[attr-defined]
    yield tc
    channel_store.close()


class TestChannelListAPI:
    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/channels")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_create(self, client: TestClient):
        client.post("/api/channels", json={"name": "Test Channel", "slug": "test"})
        resp = client.get("/api/channels")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["slug"] == "test"


class TestChannelCreateAPI:
    def test_create_with_slug(self, client: TestClient):
        resp = client.post(
            "/api/channels",
            json={"name": "Daily Report", "slug": "daily-report"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["slug"] == "daily-report"
        assert data["name"] == "Daily Report"
        assert data["conversation_id"] != ""

    def test_create_without_slug_auto_generates(self, client: TestClient):
        resp = client.post(
            "/api/channels",
            json={"name": "My Channel"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["slug"] == "my-channel"

    def test_create_duplicate_slug_returns_409(self, client: TestClient):
        client.post("/api/channels", json={"name": "First", "slug": "test"})
        resp = client.post("/api/channels", json={"name": "Second", "slug": "test"})
        assert resp.status_code == 409

    def test_create_with_description(self, client: TestClient):
        resp = client.post(
            "/api/channels",
            json={"name": "Test", "slug": "test", "description": "A test"},
        )
        assert resp.status_code == 201
        assert resp.json()["description"] == "A test"


class TestChannelGetAPI:
    def test_get_existing(self, client: TestClient):
        client.post("/api/channels", json={"name": "Test", "slug": "test"})
        resp = client.get("/api/channels/test")
        assert resp.status_code == 200
        assert resp.json()["slug"] == "test"

    def test_get_nonexistent_returns_404(self, client: TestClient):
        resp = client.get("/api/channels/nope")
        assert resp.status_code == 404


class TestChannelUpdateAPI:
    def test_update_name(self, client: TestClient):
        client.post("/api/channels", json={"name": "Old", "slug": "test"})
        resp = client.put("/api/channels/test", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_update_description(self, client: TestClient):
        client.post("/api/channels", json={"name": "Test", "slug": "test"})
        resp = client.put("/api/channels/test", json={"description": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated"

    def test_update_nonexistent_returns_404(self, client: TestClient):
        resp = client.put("/api/channels/nope", json={"name": "X"})
        assert resp.status_code == 404

    def test_update_no_fields_returns_400(self, client: TestClient):
        client.post("/api/channels", json={"name": "Test", "slug": "test"})
        resp = client.put("/api/channels/test", json={})
        assert resp.status_code == 400


class TestChannelDeleteAPI:
    def test_delete_existing(self, client: TestClient):
        client.post("/api/channels", json={"name": "Test", "slug": "test"})
        resp = client.delete("/api/channels/test")
        assert resp.status_code == 204
        # Verify it's gone
        assert client.get("/api/channels/test").status_code == 404

    def test_delete_nonexistent_returns_404(self, client: TestClient):
        resp = client.delete("/api/channels/nope")
        assert resp.status_code == 404


class TestChannelPromoteAPI:
    def test_promote_conversation(self, client: TestClient):
        conv_store: _MemoryConvStore = client._conv_store  # type: ignore[attr-defined]
        conv = ConversationData.new("system prompt")
        conv_store.save(conv)

        resp = client.post(
            "/api/channels/promote",
            json={
                "conversation_id": conv.id,
                "slug": "promoted",
                "name": "Promoted Channel",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["slug"] == "promoted"
        assert data["conversation_id"] == conv.id

    def test_promote_auto_generates_slug(self, client: TestClient):
        conv_store: _MemoryConvStore = client._conv_store  # type: ignore[attr-defined]
        conv = ConversationData.new("system")
        conv_store.save(conv)

        resp = client.post(
            "/api/channels/promote",
            json={"conversation_id": conv.id, "name": "My Channel"},
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "my-channel"

    def test_promote_duplicate_slug_returns_409(self, client: TestClient):
        conv_store: _MemoryConvStore = client._conv_store  # type: ignore[attr-defined]
        # Create channel first
        client.post("/api/channels", json={"name": "Existing", "slug": "existing"})
        # Try to promote with same slug
        conv = ConversationData.new("system")
        conv_store.save(conv)
        resp = client.post(
            "/api/channels/promote",
            json={"conversation_id": conv.id, "slug": "existing", "name": "New"},
        )
        assert resp.status_code == 409

    def test_promote_nonexistent_conversation_returns_404(self, client: TestClient):
        resp = client.post(
            "/api/channels/promote",
            json={"conversation_id": "fake-id", "slug": "test", "name": "Test"},
        )
        assert resp.status_code == 404
