"""First-run bootstrap — copy rows from legacy per-module SQLite files.

Historically, Tank wrote each module's data to its own SQLite file:

  ~/.tank/conversations.db           → conversations table
  ~/.tank/channels/channels.db       → channels, channel_read_state
  ~/.tank/jobs/jobs.db               → jobs, job_runs
  ../data/speakers.db                → speakers, embeddings

After the ORM unification all of these live in a single ``tank.db``.
This module handles the one-off migration.

Behaviour:
  * Runs after :func:`run_migrations` so the destination schema exists.
  * Idempotent: if any destination table already has rows, the copy for
    that table is skipped.
  * Sources missing on disk are silently skipped (new install path).
  * Copied-from sources are renamed to ``<path>.bak`` (and their WAL/SHM
    sidecars cleaned up) so a second boot doesn't re-import stale data.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select

from .base import Base
from .database import Database
from .models import (
    ChannelReadStateRow,
    ChannelRow,
    ConversationRow,
    EmbeddingRow,
    JobRow,
    JobRunRow,
    SpeakerRow,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LegacySource:
    """A legacy SQLite DB and the ORM tables it feeds into."""

    path: Path
    description: str
    tables: tuple[str, ...]  # source table names to copy


def default_legacy_sources(
    *,
    home: Path | None = None,
    speakers_db: Path | None = None,
) -> list[LegacySource]:
    """Return the known legacy DB locations.

    ``home`` overrides ``~`` (useful for tests). ``speakers_db`` overrides
    the ``backend/data/speakers.db`` default.
    """
    tilde = home if home is not None else Path("~").expanduser()
    speakers = speakers_db if speakers_db is not None else Path("../data/speakers.db")
    return [
        LegacySource(
            path=tilde / ".tank" / "conversations.db",
            description="conversations",
            tables=("conversations",),
        ),
        LegacySource(
            path=tilde / ".tank" / "channels" / "channels.db",
            description="channels",
            tables=("channels", "channel_read_state"),
        ),
        LegacySource(
            path=tilde / ".tank" / "jobs" / "jobs.db",
            description="jobs",
            tables=("jobs", "job_runs"),
        ),
        LegacySource(
            path=speakers.expanduser().resolve() if speakers.is_absolute() else speakers,
            description="speakers",
            tables=("speakers", "embeddings"),
        ),
    ]


# Map source table → ORM row class. Defined once so both the copier
# and the "is destination empty?" check agree on what a table is.
_TABLE_TO_MODEL: dict[str, type[Any]] = {
    "conversations": ConversationRow,
    "channels": ChannelRow,
    "channel_read_state": ChannelReadStateRow,
    "jobs": JobRow,
    "job_runs": JobRunRow,
    "speakers": SpeakerRow,
    "embeddings": EmbeddingRow,
}


@dataclass(frozen=True)
class BootstrapResult:
    """Summary of a bootstrap run. Useful for logging and tests."""

    copied: dict[str, int]          # {table_name: row_count}
    skipped: dict[str, str]         # {table_name: reason}
    renamed: list[Path]             # legacy .db files renamed to .bak


def bootstrap_legacy_data(
    db: Database,
    sources: list[LegacySource] | None = None,
) -> BootstrapResult:
    """Copy rows from any legacy DB into ``db`` and rename sources to ``.bak``.

    Safe to call on every startup: if destination tables already contain
    data, the copy is skipped for those tables. If no legacy files exist
    at all, this is a no-op.
    """
    resolved_sources = sources if sources is not None else default_legacy_sources()

    copied: dict[str, int] = {}
    skipped: dict[str, str] = {}
    renamed: list[Path] = []

    for source in resolved_sources:
        if not source.path.exists():
            skipped[source.description] = "source missing"
            continue

        rows_copied = _copy_source(db, source, copied, skipped)
        if rows_copied >= 0:  # -1 = error, 0 = nothing to copy but source was read OK
            _rename_to_bak(source.path, renamed)

    result = BootstrapResult(copied=copied, skipped=skipped, renamed=renamed)
    if copied:
        logger.info("Bootstrap copied rows: %s", copied)
    if renamed:
        logger.info("Bootstrap renamed legacy DBs: %s", [str(p) for p in renamed])
    return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _copy_source(
    db: Database,
    source: LegacySource,
    copied: dict[str, int],
    skipped: dict[str, str],
) -> int:
    """Open ``source`` (read-only), copy known tables, return total rows copied.

    Returns -1 if the source was unreadable (so callers leave the file
    in place for human investigation).
    """
    total = 0
    try:
        src = sqlite3.connect(f"file:{source.path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        logger.warning("Could not open legacy DB %s: %s", source.path, exc)
        skipped[source.description] = f"open failed: {exc}"
        return -1

    try:
        src.row_factory = sqlite3.Row
        with db.session() as session:
            for table in source.tables:
                model = _TABLE_TO_MODEL.get(table)
                if model is None:
                    skipped[table] = "unknown destination table"
                    continue

                if _destination_has_rows(session, model):
                    skipped[table] = "destination already populated"
                    continue

                n = _copy_table(src, session, table, model)
                if n > 0:
                    copied[table] = n
                    total += n
    finally:
        src.close()

    return total


def _destination_has_rows(session: Any, model: type[Any]) -> bool:
    count = session.execute(select(func.count()).select_from(model)).scalar() or 0
    return count > 0


def _copy_table(
    src: sqlite3.Connection,
    session: Any,
    table: str,
    model: type[Any],
) -> int:
    """Copy rows from ``src.<table>`` into ``model``'s table via ORM insert."""
    # Columns the ORM knows about. We only read these from the legacy row,
    # so unknown legacy columns (if any) are ignored safely.
    orm_columns = {col.name for col in Base.metadata.tables[table].columns}

    try:
        rows = src.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
    except sqlite3.OperationalError as exc:
        logger.warning("Legacy table %s missing or unreadable: %s", table, exc)
        return 0

    if not rows:
        return 0

    payload = [{k: row[k] for k in row.keys() if k in orm_columns} for row in rows]  # noqa: SIM118
    session.execute(insert(model), payload)
    logger.info("Copied %d rows into %s", len(payload), table)
    return len(payload)


def _rename_to_bak(path: Path, renamed: list[Path]) -> None:
    """Rename a legacy DB (and its WAL/SHM sidecars) to ``.bak``."""
    import contextlib

    backup = path.with_suffix(path.suffix + ".bak")
    try:
        path.rename(backup)
        renamed.append(backup)
    except OSError as exc:
        logger.warning("Could not rename %s to %s: %s", path, backup, exc)
        return

    # WAL / SHM journals are stale once the main file is gone — move them
    # alongside the .bak so future runs don't see phantom data.
    for sidecar_suffix in ("-wal", "-shm"):
        sidecar = path.with_suffix(path.suffix + sidecar_suffix)
        if sidecar.exists():
            with contextlib.suppress(OSError):
                sidecar.rename(backup.with_suffix(backup.suffix + sidecar_suffix))
