"""ConnectorIdentityStore — ORM-backed persistence for platform-identity mappings.

Maps ``(platform, external_id)`` to an internal ``session_id``. Used by
:class:`SessionMapper` to resume conversations across connector
restarts — when a Telegram user messages Tank twice a week apart, the
second message lands in the same Assistant session as the first.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..persistence import Database
from ..persistence.models import ConnectorIdentityRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConnectorIdentityRecord:
    """Stored mapping of a platform identity to a Tank session."""

    platform: str
    external_id: str
    session_id: str
    created_at: str


class ConnectorIdentityStore:
    """ORM-backed store for connector identity → session mappings."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, platform: str, external_id: str) -> ConnectorIdentityRecord | None:
        """Return the stored record for ``(platform, external_id)``, or ``None``."""
        with self._db.session() as s:
            row = s.execute(
                select(ConnectorIdentityRow).where(
                    ConnectorIdentityRow.platform == platform,
                    ConnectorIdentityRow.external_id == external_id,
                )
            ).scalar_one_or_none()

            if row is None:
                return None

            return ConnectorIdentityRecord(
                platform=row.platform,
                external_id=row.external_id,
                session_id=row.session_id,
                created_at=row.created_at,
            )

    def put_if_absent(
        self,
        platform: str,
        external_id: str,
        session_id: str,
    ) -> ConnectorIdentityRecord:
        """Insert a new identity → session mapping, or return the existing one.

        Idempotent under concurrency: if two connector callbacks race to
        resolve the same identity, exactly one row is created and both
        callers see the same ``session_id``.
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._db.session() as s:
            # SQLite ON CONFLICT DO NOTHING → safe under concurrent writers.
            stmt = (
                sqlite_insert(ConnectorIdentityRow)
                .values(
                    platform=platform,
                    external_id=external_id,
                    session_id=session_id,
                    created_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=["platform", "external_id"],
                )
            )
            s.execute(stmt)
            s.commit()

            # Re-read to return the row that actually won the race.
            row = s.execute(
                select(ConnectorIdentityRow).where(
                    ConnectorIdentityRow.platform == platform,
                    ConnectorIdentityRow.external_id == external_id,
                )
            ).scalar_one()

            return ConnectorIdentityRecord(
                platform=row.platform,
                external_id=row.external_id,
                session_id=row.session_id,
                created_at=row.created_at,
            )

    def delete(self, platform: str, external_id: str) -> bool:
        """Delete a mapping. Returns ``True`` if a row was deleted."""
        from sqlalchemy import delete

        with self._db.session() as s:
            result = s.execute(
                delete(ConnectorIdentityRow).where(
                    ConnectorIdentityRow.platform == platform,
                    ConnectorIdentityRow.external_id == external_id,
                )
            )
            s.commit()
            # SQLAlchemy's CursorResult exposes rowcount; the generic Result
            # stub doesn't. Cast via getattr so pyright sees a concrete type.
            rowcount: int = getattr(result, "rowcount", 0) or 0
            return rowcount > 0
