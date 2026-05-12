"""DynamicAllowlistStore — ORM-backed persistence for admin-granted allowlist entries.

Separate from the static, config-declared allowlist rules (which live in
``ConnectorAllowlistConfig``). Rows in this store are created at runtime
by the :class:`ApprovalBroker` when an admin clicks **Allow forever** on
an approval prompt. They're consulted by
:class:`ConnectorAllowlistPolicy.evaluate` *before* any rule scan, so a
dynamic grant short-circuits to ``ALLOW`` regardless of the configured
``default``.

The composite primary key makes :meth:`grant` idempotent at the DB
layer: repeated grants for the same ``(instance, platform, external_id)``
triple are rejected with an IntegrityError, which the store catches and
treats as a successful no-op — useful because admins may hit the
"Allow forever" button twice by accident, or two concurrent approval
clicks may race.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..persistence import Database
from ..persistence.models import ConnectorDynamicAllowlistRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DynamicAllowlistGrant:
    """Snapshot of one admin-granted allowlist entry."""

    instance_name: str
    platform: str
    external_id: str
    granted_by: str
    created_at: str


class DynamicAllowlistStore:
    """ORM-backed store for admin-granted allowlist entries.

    The store is scoped to an app-wide :class:`Database` — one store
    instance is built at startup and shared across every connector.
    Per-instance isolation comes from the ``instance_name`` column, not
    from separate store objects.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def has(
        self,
        *,
        instance_name: str,
        platform: str,
        external_id: str,
    ) -> bool:
        """Return ``True`` iff an admin has granted this identity access.

        Called on every inbound message for connectors with
        ``REQUIRE_APPROVAL`` allowlists, so the path stays lean — a
        single ``SELECT 1`` with a composite primary-key hit.
        """
        with self._db.session() as s:
            row = s.execute(
                select(ConnectorDynamicAllowlistRow.instance_name).where(
                    ConnectorDynamicAllowlistRow.instance_name == instance_name,
                    ConnectorDynamicAllowlistRow.platform == platform,
                    ConnectorDynamicAllowlistRow.external_id == external_id,
                )
            ).first()
            return row is not None

    def grant(
        self,
        *,
        instance_name: str,
        platform: str,
        external_id: str,
        granted_by: str,
    ) -> DynamicAllowlistGrant:
        """Record an admin grant. Idempotent.

        Repeated calls with the same ``(instance, platform, external_id)``
        triple preserve the *first* ``granted_by`` + ``created_at`` —
        the approval record should reflect when access was originally
        granted, not the last re-grant.
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._db.session() as s:
            stmt = (
                sqlite_insert(ConnectorDynamicAllowlistRow)
                .values(
                    instance_name=instance_name,
                    platform=platform,
                    external_id=external_id,
                    granted_by=granted_by,
                    created_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "instance_name", "platform", "external_id",
                    ],
                )
            )
            s.execute(stmt)
            s.commit()

            # Re-read to return the row that actually won the race —
            # a concurrent grant would otherwise make our return value
            # disagree with the persisted state.
            row = s.execute(
                select(ConnectorDynamicAllowlistRow).where(
                    ConnectorDynamicAllowlistRow.instance_name == instance_name,
                    ConnectorDynamicAllowlistRow.platform == platform,
                    ConnectorDynamicAllowlistRow.external_id == external_id,
                )
            ).scalar_one()

        return DynamicAllowlistGrant(
            instance_name=row.instance_name,
            platform=row.platform,
            external_id=row.external_id,
            granted_by=row.granted_by,
            created_at=row.created_at,
        )

    def list_for_instance(
        self, instance_name: str,
    ) -> list[DynamicAllowlistGrant]:
        """Return all grants for one connector instance, newest first.

        Used by a future admin-UI (revocation page); exposed here so
        the store is feature-complete without needing amendment later.
        """
        with self._db.session() as s:
            rows = (
                s.execute(
                    select(ConnectorDynamicAllowlistRow)
                    .where(
                        ConnectorDynamicAllowlistRow.instance_name == instance_name,
                    )
                    .order_by(ConnectorDynamicAllowlistRow.created_at.desc())
                )
                .scalars()
                .all()
            )
        return [
            DynamicAllowlistGrant(
                instance_name=r.instance_name,
                platform=r.platform,
                external_id=r.external_id,
                granted_by=r.granted_by,
                created_at=r.created_at,
            )
            for r in rows
        ]

    def revoke(
        self,
        *,
        instance_name: str,
        platform: str,
        external_id: str,
    ) -> bool:
        """Remove a grant. Returns ``True`` if a row was deleted.

        Phase 10 exposes ``revoke`` but doesn't hook it into any UI —
        it's here so the store is feature-complete and so tests can
        cover it.
        """
        with self._db.session() as s:
            result = s.execute(
                delete(ConnectorDynamicAllowlistRow).where(
                    ConnectorDynamicAllowlistRow.instance_name == instance_name,
                    ConnectorDynamicAllowlistRow.platform == platform,
                    ConnectorDynamicAllowlistRow.external_id == external_id,
                )
            )
            s.commit()
            # SQLAlchemy's CursorResult exposes ``rowcount``; the generic
            # ``Result`` base class's stub does not, so we reach through
            # ``getattr`` for type-checker peace of mind.
            rowcount: int = getattr(result, "rowcount", 0) or 0
            return rowcount > 0
