"""Unit tests for :class:`DynamicAllowlistStore` and its ORM row.

The store is the persistence side of Phase 10 "Allow forever" grants.
Tests here exercise idempotency, cross-instance isolation, and the
listing / revocation surface — matching the convention set by
:mod:`test_connector_identity_store` from Phase 2.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tank_backend.connectors.dynamic_allowlist import DynamicAllowlistStore
from tank_backend.persistence import Base, Database


@pytest.fixture()
def store(tmp_path: Path) -> DynamicAllowlistStore:
    """Fresh :class:`DynamicAllowlistStore` backed by an ephemeral SQLite
    file. Tables are created directly (no Alembic) since the Phase 10
    migration is smoke-tested separately — this keeps the unit tests
    narrowly scoped to the store's API surface."""
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    return DynamicAllowlistStore(db)


class TestHas:
    def test_empty_store_returns_false(self, store: DynamicAllowlistStore) -> None:
        assert store.has(
            instance_name="tg", platform="telegram", external_id="tg:user:42",
        ) is False

    def test_returns_true_after_grant(self, store: DynamicAllowlistStore) -> None:
        store.grant(
            instance_name="tg", platform="telegram",
            external_id="tg:user:42", granted_by="tg:user:99",
        )
        assert store.has(
            instance_name="tg", platform="telegram", external_id="tg:user:42",
        ) is True


class TestGrant:
    def test_roundtrip_records_granter_and_timestamp(
        self, store: DynamicAllowlistStore,
    ) -> None:
        rec = store.grant(
            instance_name="tg", platform="telegram",
            external_id="tg:user:42", granted_by="tg:user:99",
        )
        assert rec.instance_name == "tg"
        assert rec.platform == "telegram"
        assert rec.external_id == "tg:user:42"
        assert rec.granted_by == "tg:user:99"
        assert rec.created_at  # ISO timestamp populated

    def test_idempotent_preserves_original_metadata(
        self, store: DynamicAllowlistStore,
    ) -> None:
        """A second grant for the same triple is a no-op at the DB
        layer — the ``granted_by`` and ``created_at`` of the first
        grant must win. Critical for audit accuracy: 'who approved
        Alice originally?' should never be overwritten by a later
        re-approval."""
        first = store.grant(
            instance_name="tg", platform="telegram",
            external_id="tg:user:42", granted_by="tg:user:99",
        )
        second = store.grant(
            instance_name="tg", platform="telegram",
            external_id="tg:user:42", granted_by="tg:user:77",  # different admin
        )
        assert second.granted_by == first.granted_by == "tg:user:99"
        assert second.created_at == first.created_at


class TestInstanceIsolation:
    def test_grants_scoped_by_instance(
        self, store: DynamicAllowlistStore,
    ) -> None:
        """Staging and prod bots share no grants even when the
        underlying identity is identical — the composite primary key
        includes ``instance_name``."""
        store.grant(
            instance_name="staging", platform="telegram",
            external_id="tg:user:42", granted_by="tg:user:99",
        )
        assert store.has(
            instance_name="staging", platform="telegram",
            external_id="tg:user:42",
        ) is True
        assert store.has(
            instance_name="prod", platform="telegram",
            external_id="tg:user:42",
        ) is False

    def test_list_for_instance_returns_only_that_instance(
        self, store: DynamicAllowlistStore,
    ) -> None:
        store.grant(
            instance_name="tg", platform="telegram",
            external_id="tg:user:1", granted_by="tg:user:99",
        )
        store.grant(
            instance_name="tg", platform="telegram",
            external_id="tg:user:2", granted_by="tg:user:99",
        )
        store.grant(
            instance_name="slack", platform="slack",
            external_id="slack:user:U1", granted_by="slack:user:U99",
        )

        tg_grants = store.list_for_instance("tg")
        assert {g.external_id for g in tg_grants} == {"tg:user:1", "tg:user:2"}
        slack_grants = store.list_for_instance("slack")
        assert len(slack_grants) == 1


class TestRevoke:
    def test_revoke_hit_returns_true(
        self, store: DynamicAllowlistStore,
    ) -> None:
        store.grant(
            instance_name="tg", platform="telegram",
            external_id="tg:user:42", granted_by="tg:user:99",
        )
        assert store.revoke(
            instance_name="tg", platform="telegram",
            external_id="tg:user:42",
        ) is True
        assert store.has(
            instance_name="tg", platform="telegram",
            external_id="tg:user:42",
        ) is False

    def test_revoke_miss_returns_false(
        self, store: DynamicAllowlistStore,
    ) -> None:
        assert store.revoke(
            instance_name="tg", platform="telegram",
            external_id="tg:user:does-not-exist",
        ) is False

    def test_revoke_does_not_affect_other_instances(
        self, store: DynamicAllowlistStore,
    ) -> None:
        store.grant(
            instance_name="staging", platform="telegram",
            external_id="tg:user:42", granted_by="tg:user:99",
        )
        store.grant(
            instance_name="prod", platform="telegram",
            external_id="tg:user:42", granted_by="tg:user:99",
        )
        assert store.revoke(
            instance_name="staging", platform="telegram",
            external_id="tg:user:42",
        ) is True
        # prod untouched.
        assert store.has(
            instance_name="prod", platform="telegram",
            external_id="tg:user:42",
        ) is True
