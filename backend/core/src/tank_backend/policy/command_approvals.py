"""CommandApprovalStore — persistence for user-approved command patterns.

When a user interactively approves an unknown command, the base command
(extracted executable name) is stored here. On subsequent sessions, the
``CommandSecurityPolicy`` checks this store before falling through to
REQUIRE_APPROVAL, effectively making the approval durable.

Pattern: mirrors ``DynamicAllowlistStore`` (ORM-backed, idempotent grant).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..persistence import Database
from ..persistence.models import CommandApprovalRow

logger = logging.getLogger(__name__)


class CommandApprovalStore:
    """ORM-backed store for durable command approvals.

    The store is scoped to the app-wide :class:`Database`.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        # In-memory cache for fast lookups (loaded once at init)
        self._cache: set[str] | None = None

    def _load_cache(self) -> set[str]:
        """Load all approved patterns into memory."""
        if self._cache is not None:
            return self._cache
        with self._db.session() as session:
            rows = session.execute(
                select(CommandApprovalRow.command_pattern)
            ).scalars().all()
            self._cache = set(rows)
        logger.info("CommandApprovalStore: loaded %d durable approvals", len(self._cache))
        return self._cache

    def has(self, base_command: str) -> bool:
        """Check if a base command has been previously approved."""
        cache = self._load_cache()
        return base_command in cache

    def grant(self, base_command: str, session_id: str = "") -> None:
        """Persist a command approval. Idempotent."""
        cache = self._load_cache()
        if base_command in cache:
            return

        now = datetime.now(timezone.utc).isoformat()
        with self._db.session() as session:
            stmt = sqlite_insert(CommandApprovalRow).values(
                command_pattern=base_command,
                session_id=session_id,
                created_at=now,
            ).on_conflict_do_nothing()
            session.execute(stmt)
            session.commit()

        cache.add(base_command)
        logger.info("CommandApprovalStore: granted '%s'", base_command)

    def revoke(self, base_command: str) -> bool:
        """Remove a durable approval. Returns True if it existed."""
        cache = self._load_cache()
        if base_command not in cache:
            return False

        from sqlalchemy import delete

        with self._db.session() as session:
            session.execute(
                delete(CommandApprovalRow).where(
                    CommandApprovalRow.command_pattern == base_command
                )
            )
            session.commit()

        cache.discard(base_command)
        logger.info("CommandApprovalStore: revoked '%s'", base_command)
        return True

    def list_all(self) -> list[str]:
        """Return all approved command patterns."""
        return sorted(self._load_cache())
