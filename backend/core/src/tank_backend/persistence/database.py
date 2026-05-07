"""Database — unified SQLAlchemy engine + session factory for Tank.

One :class:`Database` instance lives in the composition root
(``api/server.py``) and is passed to each store via dependency injection.
Stores use :meth:`Database.session` as a context manager that handles
``commit`` / ``rollback`` / ``close`` for every unit of work.

SQLite note: WAL mode and foreign-key enforcement are turned on per
connection via an engine-level ``connect`` event listener — this is the
idiomatic SQLAlchemy way to apply PRAGMAs to every new connection taken
from the pool.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


_SQLITE_SCHEMES = ("sqlite+pysqlite://", "sqlite://")


def _expand_sqlite_url(url: str) -> str:
    """Expand ``~`` and resolve the path inside a SQLite URL, ensure parent exists.

    Accepts forms like ``sqlite+pysqlite:///~/.tank/tank.db`` and returns
    ``sqlite+pysqlite:////Users/you/.tank/tank.db``. In-memory URLs pass through.
    """
    for scheme in _SQLITE_SCHEMES:
        if not url.startswith(scheme):
            continue
        path_part = url[len(scheme) :]
        # Three slashes after scheme => relative; four => absolute. In-memory: ":memory:".
        if path_part.startswith("/:memory:") or path_part == "/:memory:":
            return url
        # Strip the leading slash that precedes the filesystem path
        leading_slash = path_part.startswith("/")
        raw_path = path_part[1:] if leading_slash else path_part
        if not raw_path or raw_path == ":memory:":
            return url
        resolved = Path(raw_path).expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return f"{scheme}/{resolved}"
    return url


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enable WAL + foreign keys on every SQLite connection.

    This hook is a no-op on non-SQLite engines (the attribute check fails).
    """
    try:
        import sqlite3

        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
    except ImportError:  # pragma: no cover
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


class Database:
    """Owns the SQLAlchemy engine and provides transactional sessions."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        resolved = _expand_sqlite_url(url)
        self._url = resolved
        # ``future=True`` is the default in 2.0 but explicit keeps intent clear.
        self._engine: Engine = create_engine(resolved, echo=echo, future=True)
        self._session_factory = sessionmaker(
            bind=self._engine, expire_on_commit=False, future=True,
        )
        logger.info("Database initialised (url=%s)", self._safe_url())

    @property
    def engine(self) -> Engine:
        """Underlying SQLAlchemy Engine (useful for Alembic + tests)."""
        return self._engine

    @property
    def url(self) -> str:
        """Resolved URL (with ``~`` expanded)."""
        return self._url

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a session, commit on success, rollback on exception, always close.

        Usage::

            with db.session() as s:
                s.add(row)
                # commit happens automatically on clean exit
        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Close all pooled connections. Call at shutdown."""
        self._engine.dispose()

    def _safe_url(self) -> str:
        """Return the URL without credentials for logging."""
        if "@" not in self._url:
            return self._url
        prefix, _, rest = self._url.partition("://")
        _, _, host_part = rest.rpartition("@")
        return f"{prefix}://***@{host_part}"
