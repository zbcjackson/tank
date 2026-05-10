"""Unit tests for the connector identity store."""

from __future__ import annotations

from pathlib import Path

import pytest

from tank_backend.connectors.identity_store import ConnectorIdentityStore
from tank_backend.persistence import Base, Database


@pytest.fixture()
def store(tmp_path: Path) -> ConnectorIdentityStore:
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    return ConnectorIdentityStore(db)


class TestConnectorIdentityStore:
    def test_empty_lookup_returns_none(self, store: ConnectorIdentityStore) -> None:
        assert store.get("telegram", "tg:user:1") is None

    def test_put_then_get_roundtrip(self, store: ConnectorIdentityStore) -> None:
        rec = store.put_if_absent("telegram", "tg:user:1", "sess-abc")
        assert rec.session_id == "sess-abc"
        assert rec.platform == "telegram"
        assert rec.external_id == "tg:user:1"

        fetched = store.get("telegram", "tg:user:1")
        assert fetched is not None
        assert fetched.session_id == "sess-abc"

    def test_put_if_absent_is_idempotent(self, store: ConnectorIdentityStore) -> None:
        """Re-inserting the same identity must not overwrite the session id."""
        store.put_if_absent("telegram", "tg:user:1", "sess-abc")
        rec2 = store.put_if_absent("telegram", "tg:user:1", "sess-xyz")

        assert rec2.session_id == "sess-abc"

    def test_different_identities_are_isolated(
        self, store: ConnectorIdentityStore,
    ) -> None:
        a = store.put_if_absent("telegram", "tg:user:1", "sess-a")
        b = store.put_if_absent("telegram", "tg:user:2", "sess-b")

        assert a.session_id == "sess-a"
        assert b.session_id == "sess-b"

    def test_same_external_id_different_platforms_isolated(
        self, store: ConnectorIdentityStore,
    ) -> None:
        a = store.put_if_absent("telegram", "12345", "sess-tg")
        b = store.put_if_absent("slack", "12345", "sess-sl")

        assert a.session_id == "sess-tg"
        assert b.session_id == "sess-sl"

    def test_delete_removes_row(self, store: ConnectorIdentityStore) -> None:
        store.put_if_absent("telegram", "tg:user:1", "sess-abc")
        assert store.delete("telegram", "tg:user:1") is True
        assert store.get("telegram", "tg:user:1") is None

    def test_delete_absent_returns_false(
        self, store: ConnectorIdentityStore,
    ) -> None:
        assert store.delete("telegram", "tg:user:1") is False
