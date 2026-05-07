"""Programmatic Alembic runner.

Backend startup calls :func:`run_migrations` to bring the DB to ``head``
before FastAPI starts serving requests. Idempotent and fast — if already
at head, does nothing.

This replaces the hand-rolled ``CREATE TABLE IF NOT EXISTS`` / ``ALTER
TABLE`` logic that used to live inside each store.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_ALEMBIC_INI = _MIGRATIONS_DIR / "alembic.ini"


def _build_config(url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    # env.py reads ``-x url=...`` via ``context.get_x_argument`` — pass the
    # override via an argparse.Namespace which is what cmd_opts expects.
    cfg.cmd_opts = argparse.Namespace(x=[f"url={url}"])
    return cfg


def run_migrations(url: str) -> None:
    """Upgrade the database at ``url`` to head. Safe to call every startup.

    If the database already contains Tank tables but has never been
    tracked by Alembic (e.g. a pre-migration install using plain
    ``CREATE TABLE``), we stamp it to the current head rather than
    attempt to re-create the tables. This makes the first migration
    run idempotent for existing installations.
    """
    from sqlalchemy import create_engine, inspect

    from .database import _expand_sqlite_url

    resolved = _expand_sqlite_url(url)
    logger.info("Running database migrations (url=%s)", _safe(resolved))

    cfg = _build_config(resolved)

    # Auto-stamp legacy installations that pre-date Alembic tracking.
    engine = create_engine(resolved, future=True)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if "alembic_version" not in tables and _TANK_TABLES.issubset(tables):
            logger.info("Existing Tank schema detected; stamping at head")
            command.stamp(cfg, "head")
            return
    finally:
        engine.dispose()

    command.upgrade(cfg, "head")
    logger.info("Database migrations complete")


# Tables that mark a database as "already a Tank DB". Used by run_migrations
# to detect legacy installs that were created before Alembic tracking.
_TANK_TABLES = {
    "conversations",
    "channels",
    "channel_read_state",
    "jobs",
    "job_runs",
    "speakers",
    "embeddings",
}


def create_revision(url: str, message: str, *, autogenerate: bool = True) -> None:
    """Generate a new migration script. Developer tool — not called at runtime."""
    cfg = _build_config(url)
    command.revision(cfg, message=message, autogenerate=autogenerate)


def _safe(url: str) -> str:
    if "@" not in url:
        return url
    prefix, _, rest = url.partition("://")
    _, _, host = rest.rpartition("@")
    return f"{prefix}://***@{host}"
