"""Tests for persistence.migrate — root logger restoration after Alembic."""

from __future__ import annotations

import logging


def test_run_migrations_restores_root_logger_level(tmp_path):
    """Alembic's fileConfig sets root logger to WARN.

    ``run_migrations`` must restore the caller's level so backend INFO
    logging survives the migration call.
    """
    from tank_backend.persistence.migrate import run_migrations

    root = logging.getLogger()
    prior = root.level
    try:
        root.setLevel(logging.INFO)
        run_migrations(f"sqlite+pysqlite:///{tmp_path}/tank.db")
        assert root.level == logging.INFO
    finally:
        root.setLevel(prior)


def test_run_migrations_restores_root_logger_at_debug(tmp_path):
    """Same property at DEBUG level — the restoration is symmetric."""
    from tank_backend.persistence.migrate import run_migrations

    root = logging.getLogger()
    prior = root.level
    try:
        root.setLevel(logging.DEBUG)
        run_migrations(f"sqlite+pysqlite:///{tmp_path}/tank.db")
        assert root.level == logging.DEBUG
    finally:
        root.setLevel(prior)
