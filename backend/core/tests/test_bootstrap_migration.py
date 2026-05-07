"""Tests for the first-run bootstrap migration (Phase 2)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import numpy as np

from tank_backend.persistence import (
    Database,
    bootstrap_legacy_data,
    run_migrations,
)
from tank_backend.persistence.bootstrap import LegacySource

# ---------------------------------------------------------------------------
# Helpers to build synthetic legacy DBs — mirrors the exact schema each
# legacy store used to create. If a schema mismatch appears the test will
# fail loudly rather than silently swallow the missing data.
# ---------------------------------------------------------------------------


def _make_conversations_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE conversations (
            conversation_id TEXT PRIMARY KEY,
            start_time TEXT NOT NULL,
            pid INTEGER NOT NULL,
            messages TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO conversations VALUES (?, ?, ?, ?, ?)",
        ("conv1", "2026-01-01T00:00:00+00:00", 123,
         json.dumps([{"role": "user", "content": "hi"}]), time.time()),
    )
    conn.commit()
    conn.close()


def _make_channels_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE channels (
            slug TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            auto_created INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE channel_read_state (
            slug TEXT PRIMARY KEY REFERENCES channels(slug) ON DELETE CASCADE,
            last_read_message_count INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.execute(
        "INSERT INTO channels VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("general", "General", "conv1", "Main channel", 0,
         "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO channel_read_state VALUES (?, ?)",
        ("general", 3),
    )
    conn.commit()
    conn.close()


def _make_jobs_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            prompt TEXT NOT NULL,
            schedule TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            origin TEXT NOT NULL DEFAULT 'api',
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE job_runs (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            output_path TEXT,
            error TEXT,
            stats_json TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("job1", "daily", "say hi", "0 9 * * *", 1, "seed",
         json.dumps({"id": "job1"}),
         "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO job_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("run1", "job1", "succeeded",
         "2026-01-02T00:00:00+00:00", "2026-01-02T00:01:00+00:00",
         None, None, None),
    )
    conn.commit()
    conn.close()


def _make_speakers_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE speakers (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            embedding BLOB NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES speakers(user_id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        "INSERT INTO speakers VALUES (?, ?, ?, ?)",
        ("u1", "Jackson", 1700000000.0, 1700000000.0),
    )
    emb = np.array([0.1, 0.2, 0.3], dtype=np.float32).tobytes()
    conn.execute(
        "INSERT INTO embeddings (user_id, embedding, created_at) VALUES (?, ?, ?)",
        ("u1", emb, 1700000000.0),
    )
    conn.commit()
    conn.close()


def _build_sources(home: Path, speakers_path: Path) -> list[LegacySource]:
    return [
        LegacySource(
            path=home / ".tank" / "conversations.db",
            description="conversations",
            tables=("conversations",),
        ),
        LegacySource(
            path=home / ".tank" / "channels" / "channels.db",
            description="channels",
            tables=("channels", "channel_read_state"),
        ),
        LegacySource(
            path=home / ".tank" / "jobs" / "jobs.db",
            description="jobs",
            tables=("jobs", "job_runs"),
        ),
        LegacySource(
            path=speakers_path,
            description="speakers",
            tables=("speakers", "embeddings"),
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bootstrap_copies_all_four_legacy_dbs(tmp_path: Path) -> None:
    """End-to-end: 4 legacy DBs → unified DB, rows land in each table."""
    home = tmp_path / "home"
    speakers = tmp_path / "data" / "speakers.db"
    _make_conversations_db(home / ".tank" / "conversations.db")
    _make_channels_db(home / ".tank" / "channels" / "channels.db")
    _make_jobs_db(home / ".tank" / "jobs" / "jobs.db")
    _make_speakers_db(speakers)

    url = f"sqlite+pysqlite:///{tmp_path}/tank.db"
    run_migrations(url)
    db = Database(url)

    sources = _build_sources(home, speakers)
    result = bootstrap_legacy_data(db, sources=sources)

    assert result.copied == {
        "conversations": 1,
        "channels": 1,
        "channel_read_state": 1,
        "jobs": 1,
        "job_runs": 1,
        "speakers": 1,
        "embeddings": 1,
    }
    # All 4 legacy files should have been renamed to .bak
    assert len(result.renamed) == 4
    assert all(p.suffix == ".bak" for p in result.renamed)


def test_bootstrap_skips_when_destination_already_populated(tmp_path: Path) -> None:
    """Re-running after rows exist in dest table must not re-import."""
    home = tmp_path / "home"
    _make_conversations_db(home / ".tank" / "conversations.db")

    url = f"sqlite+pysqlite:///{tmp_path}/tank.db"
    run_migrations(url)
    db = Database(url)

    sources = _build_sources(home, tmp_path / "nope.db")

    # First run — copies one row.
    first = bootstrap_legacy_data(db, sources=sources)
    assert first.copied.get("conversations") == 1

    # Re-create the source (simulating a backup being restored) at the .bak
    # location's pre-rename path and re-run. The destination already has
    # the row, so we expect a skip even though the source has data.
    _make_conversations_db(home / ".tank" / "conversations.db")
    second = bootstrap_legacy_data(db, sources=sources)
    assert "conversations" not in second.copied
    assert second.skipped.get("conversations") == "destination already populated"


def test_bootstrap_noop_when_no_legacy_files(tmp_path: Path) -> None:
    """Fresh install (no legacy DBs) is a clean no-op."""
    url = f"sqlite+pysqlite:///{tmp_path}/tank.db"
    run_migrations(url)
    db = Database(url)

    sources = _build_sources(tmp_path / "home", tmp_path / "nope.db")
    result = bootstrap_legacy_data(db, sources=sources)

    assert result.copied == {}
    assert result.renamed == []
    assert all("source missing" in r for r in result.skipped.values())


def test_bootstrap_preserves_data_roundtrip(tmp_path: Path) -> None:
    """Data copied should read back identical to what the legacy store wrote."""
    home = tmp_path / "home"
    speakers_src = tmp_path / "data" / "speakers.db"
    _make_speakers_db(speakers_src)

    url = f"sqlite+pysqlite:///{tmp_path}/tank.db"
    run_migrations(url)
    db = Database(url)

    sources = _build_sources(home, speakers_src)
    bootstrap_legacy_data(db, sources=sources)

    from sqlalchemy import select

    from tank_backend.persistence.models import EmbeddingRow, SpeakerRow

    with db.session() as s:
        speaker = s.execute(select(SpeakerRow).where(SpeakerRow.user_id == "u1")).scalar_one()
        assert speaker.name == "Jackson"
        embs = s.execute(select(EmbeddingRow).where(EmbeddingRow.user_id == "u1")).scalars().all()
        assert len(embs) == 1
        arr = np.frombuffer(embs[0].embedding, dtype=np.float32)
        assert arr.tolist() == [float(np.float32(v)) for v in (0.1, 0.2, 0.3)]
