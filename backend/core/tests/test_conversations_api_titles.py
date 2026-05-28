"""Tests for the conversations REST API — title PATCH + regenerate."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tank_backend.context.conversation import ConversationData
from tank_backend.context.store import ConversationStore


class _MemoryConvStore(ConversationStore):
    def __init__(self) -> None:
        self._data: dict[str, ConversationData] = {}

    def save(self, conversation: ConversationData) -> None:
        self._data[conversation.id] = conversation

    def load(self, conversation_id: str) -> ConversationData | None:
        return self._data.get(conversation_id)

    def list_conversations(self):
        from tank_backend.context.conversation import ConversationSummary

        return [
            ConversationSummary(
                id=c.id,
                start_time=c.start_time,
                message_count=len(c.messages),
                updated_at=c.start_time,
                preview="",
                title=c.title,
            )
            for c in self._data.values()
        ]

    def delete(self, conversation_id: str) -> None:
        self._data.pop(conversation_id, None)

    def find_latest(self) -> ConversationData | None:
        return None


class _StubTitleGenerator:
    def __init__(self, return_value: str | None = "Generated title") -> None:
        self._return_value = return_value
        self.calls: list[str] = []

    async def generate(self, conversation_id: str) -> str | None:
        self.calls.append(conversation_id)
        store = _stub_state["store"]
        title = self._return_value
        if title is not None and store is not None:
            conv = store.load(conversation_id)
            if conv is not None:
                conv.title = title
                store.save(conv)
        return title


_stub_state: dict[str, _MemoryConvStore | None] = {"store": None}


@pytest.fixture()
def client(tmp_path: Path):
    from tank_backend.api import deps
    from tank_backend.api.server import app
    from tank_backend.config.context import AppContext

    conv_store = _MemoryConvStore()
    _stub_state["store"] = conv_store
    title_gen = _StubTitleGenerator()

    ctx = AppContext(
        app_config=deps.app_context().app_config,
        conversation_store=conv_store,
        title_generator=title_gen,  # type: ignore[arg-type]
    )
    deps.init(ctx, deps.connection_manager())

    tc = TestClient(app, raise_server_exceptions=False)
    tc.app.extra_state = {"conv_store": conv_store, "title_gen": title_gen}  # type: ignore[attr-defined]
    yield tc, conv_store, title_gen
    _stub_state["store"] = None


def _seed(store: _MemoryConvStore, conv_id: str, title: str | None = None) -> None:
    store.save(ConversationData(
        id=conv_id,
        start_time=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
        pid=1,
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
        title=title,
    ))


class TestListIncludesTitle:
    def test_title_in_list_payload(self, client):
        tc, store, _ = client
        _seed(store, "c1", title="Existing title")
        resp = tc.get("/api/conversations")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["title"] == "Existing title"

    def test_null_title_serialised_as_null(self, client):
        tc, store, _ = client
        _seed(store, "c2")
        resp = tc.get("/api/conversations")
        assert resp.json()[0]["title"] is None


class TestPatchConversationTitle:
    def test_updates_existing_title(self, client):
        tc, store, _ = client
        _seed(store, "c1")
        resp = tc.patch("/api/conversations/c1", json={"title": "Trip planning"})
        assert resp.status_code == 200
        assert resp.json() == {"conversation_id": "c1", "title": "Trip planning"}
        assert store.load("c1").title == "Trip planning"

    def test_trims_whitespace(self, client):
        tc, store, _ = client
        _seed(store, "c1")
        resp = tc.patch("/api/conversations/c1", json={"title": "   Padded   "})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Padded"

    def test_empty_title_rejected(self, client):
        tc, store, _ = client
        _seed(store, "c1")
        resp = tc.patch("/api/conversations/c1", json={"title": "   "})
        assert resp.status_code == 400

    def test_oversize_title_rejected_at_validation(self, client):
        tc, store, _ = client
        _seed(store, "c1")
        resp = tc.patch("/api/conversations/c1", json={"title": "x" * 200})
        # Pydantic max_length blocks before our handler runs → 422.
        assert resp.status_code in (400, 422)

    def test_missing_conversation_returns_404(self, client):
        tc, _, _ = client
        resp = tc.patch("/api/conversations/missing", json={"title": "x"})
        assert resp.status_code == 404


class TestRegenerateConversationTitle:
    def test_returns_generated_title(self, client):
        tc, store, gen = client
        _seed(store, "c1")
        resp = tc.post("/api/conversations/c1/title/regenerate")
        assert resp.status_code == 200
        assert resp.json() == {"conversation_id": "c1", "title": "Generated title"}
        assert gen.calls == ["c1"]
        assert store.load("c1").title == "Generated title"

    def test_returns_404_when_conversation_missing(self, client):
        tc, _, gen = client
        resp = tc.post("/api/conversations/missing/title/regenerate")
        assert resp.status_code == 404
        assert gen.calls == []
