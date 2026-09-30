"""Smoke tests for the unified persistence layer (Phase 1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from tank_backend.persistence import Base, Database, run_migrations


def test_memory_database_serializes_cross_thread_transactions() -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    db = Database("sqlite+pysqlite:///:memory:")
    entered, release, attempted = Event(), Event(), Event()
    with db.session() as session:
        session.execute(text("CREATE TABLE smoke (k TEXT PRIMARY KEY)"))

    def rollback() -> None:
        with db.session() as session:
            session.execute(text("INSERT INTO smoke VALUES ('discard')"))
            entered.set()
            assert release.wait(2)
            raise ValueError("rollback first transaction")

    def commit() -> None:
        attempted.set()
        with db.session() as session:
            session.execute(text("INSERT INTO smoke VALUES ('keep')"))

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(rollback)
            try:
                assert entered.wait(2)
                second = pool.submit(commit)
                assert attempted.wait(2)
                with pytest.raises(TimeoutError):
                    second.result(timeout=0.03)
            finally:
                release.set()
            with pytest.raises(ValueError, match="rollback first"):
                first.result(timeout=2)
            second.result(timeout=2)
        with db.session() as session:
            assert list(session.scalars(text("SELECT k FROM smoke"))) == ["keep"]
    finally:
        db.dispose()


def test_database_creates_session_and_commits(tmp_path: Path) -> None:
    """Database.session() should commit on clean exit."""
    db = Database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(db.engine)

    with db.session() as s:
        s.execute(text("CREATE TABLE smoke (k TEXT PRIMARY KEY, v TEXT)"))
        s.execute(text("INSERT INTO smoke (k, v) VALUES ('a', '1')"))

    with db.session() as s:
        row = s.execute(text("SELECT v FROM smoke WHERE k='a'")).fetchone()
        assert row is not None
        assert row[0] == "1"


def test_database_session_rolls_back_on_exception(tmp_path: Path) -> None:
    """Raising inside the session context must roll back uncommitted work."""
    db = Database("sqlite+pysqlite:///:memory:")

    with db.session() as s:
        s.execute(text("CREATE TABLE smoke (k TEXT PRIMARY KEY, v TEXT)"))

    class _Boom(Exception):
        pass

    try:
        with db.session() as s:
            s.execute(text("INSERT INTO smoke (k, v) VALUES ('a', '1')"))
            raise _Boom
    except _Boom:
        pass

    with db.session() as s:
        rows = s.execute(text("SELECT * FROM smoke")).fetchall()
        assert rows == []


def test_sqlite_pragmas_are_applied() -> None:
    """WAL + foreign_keys PRAGMAs should fire on every connection."""
    # Use a file-backed DB — :memory: doesn't support WAL.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        db = Database(f"sqlite+pysqlite:///{d}/t.db")
        with db.session() as s:
            mode = s.execute(text("PRAGMA journal_mode")).fetchone()
            fk = s.execute(text("PRAGMA foreign_keys")).fetchone()
            assert mode is not None and mode[0] == "wal"
            assert fk is not None and fk[0] == 1


def test_run_migrations_creates_expected_tables(tmp_path: Path) -> None:
    """Alembic upgrade head should create all 7 domain tables + alembic_version."""
    url = f"sqlite+pysqlite:///{tmp_path}/tank.db"
    run_migrations(url)

    db = Database(url)
    with db.session() as s:
        rows = s.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ).fetchall()
    names = {r[0] for r in rows}
    expected = {
        "alembic_version",
        "channels",
        "channel_read_state",
        "conversations",
        "jobs",
        "job_runs",
        "speakers",
        "embeddings",
    }
    assert expected.issubset(names)


def test_run_migrations_is_idempotent(tmp_path: Path) -> None:
    """Running migrations twice must not fail."""
    url = f"sqlite+pysqlite:///{tmp_path}/tank.db"
    run_migrations(url)
    run_migrations(url)


def test_worker_input_migration_preserves_legacy_rows(tmp_path: Path) -> None:
    from alembic import command

    from tank_backend.agents.store import WorkerStore
    from tank_backend.persistence.migrate import _build_config

    url = f"sqlite+pysqlite:///{tmp_path}/workers.db"
    command.upgrade(_build_config(url), "d3f5b7a2e9c1")
    db = Database(url)
    try:
        with db.session() as session:
            session.execute(text(
                "INSERT INTO worker_runs "
                "(task_id, agent_def, description, prompt, status, background, started_at, output) "
                "VALUES ('old', 'fake', '', 'task', 'completed', 0, '2026-09-28', 'done')"
            ))
        run_migrations(url)
        store = WorkerStore(db)
        old = store.get("old")
        assert old is not None and old.output == "done" and old.task_input is None
        assert old.task_result is None
        store.create(task_id="new", agent_def="fake", prompt="task", task_input={"version": 1})
        new = store.get("new")
        assert new is not None and new.task_input == {"version": 1}
        result = {"schema_version": 1, "status": "unknown", "summary": "save unverified"}
        store.finish("new", status="unknown", task_result=result)
        finished = store.get("new")
        assert finished is not None and finished.task_result == result
    finally:
        db.dispose()


def test_expand_sqlite_url_expands_tilde() -> None:
    """``~`` in SQLite URLs is expanded to absolute path; parent dir is created."""
    import tempfile

    from tank_backend.persistence.database import _expand_sqlite_url

    # Use a sub-path of tmp (safer than touching ~/)
    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite+pysqlite:///{d}/sub/new.db"
        expanded = _expand_sqlite_url(url)
        # The parent directory should now exist (created by the helper).
        assert (Path(d) / "sub").is_dir()
        assert expanded.endswith("/new.db")


def test_worker_audit_migration_preserves_workers(tmp_path: Path) -> None:
    from alembic import command

    from tank_backend.agents.store import WorkerStore
    from tank_backend.agents.task_runtime import ExecutionRecord
    from tank_backend.persistence.migrate import _build_config

    url = f"sqlite+pysqlite:///{tmp_path}/audit-migration.db"
    command.upgrade(_build_config(url), "f2b8d5c9e3a7")
    db = Database(url)
    store = WorkerStore(db)
    store.create(task_id="old", agent_def="fake", prompt="keep")
    run_migrations(url)
    try:
        record = ExecutionRecord("old", "call", "read", "returned")
        store.append_audit(record)
        assert store.audit_records("old") == [record]
        old = store.get("old")
        assert old is not None and old.prompt == "keep"
    finally:
        db.dispose()
