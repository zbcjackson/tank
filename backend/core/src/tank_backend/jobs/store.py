"""SQLite-backed job store — definitions, run history, and scheduling state.

All data lives under ``~/.tank/jobs/`` by default.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cron import next_run_time, validate_cron
from .models import JobDefinition, JobRunResult

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "~/.tank/jobs/jobs.db"


class JobStore:
    """Persistent store for job definitions, scheduling state, and run history."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH) -> None:
        resolved = Path(db_path).expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(resolved)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL UNIQUE,
                prompt      TEXT NOT NULL,
                schedule    TEXT NOT NULL,
                enabled     INTEGER DEFAULT 1,
                origin      TEXT NOT NULL DEFAULT 'api',
                config_json TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_runs (
                id          TEXT PRIMARY KEY,
                job_id      TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                status      TEXT NOT NULL,
                started_at  TEXT,
                finished_at TEXT,
                output_path TEXT,
                error       TEXT,
                stats_json  TEXT
            );

            CREATE TABLE IF NOT EXISTS job_schedule (
                job_id      TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                next_run_at TEXT NOT NULL,
                last_run_at TEXT,
                last_status TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_job_runs_job_id ON job_runs(job_id);
            CREATE INDEX IF NOT EXISTS idx_job_schedule_next ON job_schedule(next_run_at);
        """)
        self._conn.commit()
        self._migrate_origin_column()

    # ------------------------------------------------------------------
    # Job CRUD
    # ------------------------------------------------------------------

    def save_job(self, job: JobDefinition, origin: str = "api") -> None:
        """Insert or update a job definition and its schedule."""
        now = datetime.now(timezone.utc).isoformat()
        config_json = job.to_json()

        self._conn.execute(
            """INSERT INTO jobs
               (id, name, prompt, schedule, enabled, origin,
                config_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   prompt=excluded.prompt,
                   schedule=excluded.schedule,
                   enabled=excluded.enabled,
                   config_json=excluded.config_json,
                   updated_at=excluded.updated_at
            """,
            (job.id, job.name, job.prompt, job.schedule, int(job.enabled),
             origin, config_json, job.created_at or now, now),
        )

        # Upsert schedule — compute next_run_at from cron expression
        nrt = next_run_time(job.schedule).isoformat()
        self._conn.execute(
            """INSERT INTO job_schedule (job_id, next_run_at)
               VALUES (?, ?)
               ON CONFLICT(job_id) DO UPDATE SET next_run_at=excluded.next_run_at
            """,
            (job.id, nrt),
        )
        self._conn.commit()

    def get_job(self, job_id: str) -> JobDefinition | None:
        """Fetch a job by ID."""
        row = self._conn.execute(
            "SELECT config_json FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return JobDefinition.from_json(row[0])

    def get_job_by_name(self, name: str) -> JobDefinition | None:
        """Fetch a job by its human-readable name."""
        row = self._conn.execute(
            "SELECT config_json FROM jobs WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return JobDefinition.from_json(row[0])

    def list_jobs(self, enabled_only: bool = False) -> list[JobDefinition]:
        """List all jobs, optionally filtering to enabled only."""
        query = "SELECT config_json FROM jobs"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY name"
        rows = self._conn.execute(query).fetchall()
        return [JobDefinition.from_json(r[0]) for r in rows]

    def delete_job(self, job_id: str) -> bool:
        """Delete a job and its schedule/run history. Returns True if found."""
        cursor = self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def set_enabled(self, job_id: str, enabled: bool) -> bool:
        """Enable or disable a job. Returns True if found."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "UPDATE jobs SET enabled = ?, updated_at = ? WHERE id = ?",
            (int(enabled), now, job_id),
        )
        if cursor.rowcount > 0:
            # Update config_json to keep it in sync
            row = self._conn.execute(
                "SELECT config_json FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row:
                data = json.loads(row[0])
                data["enabled"] = enabled
                data["updated_at"] = now
                self._conn.execute(
                    "UPDATE jobs SET config_json = ? WHERE id = ?",
                    (json.dumps(data), job_id),
                )
            self._conn.commit()
            return True
        return False

    # ------------------------------------------------------------------
    # Schedule management
    # ------------------------------------------------------------------

    def get_due_jobs(self, now: datetime | None = None) -> list[JobDefinition]:
        """Return enabled jobs whose next_run_at <= now."""
        if now is None:
            now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        rows = self._conn.execute(
            """SELECT j.config_json FROM jobs j
               JOIN job_schedule s ON j.id = s.job_id
               WHERE j.enabled = 1 AND s.next_run_at <= ?
               ORDER BY s.next_run_at
            """,
            (now_iso,),
        ).fetchall()
        return [JobDefinition.from_json(r[0]) for r in rows]

    def advance_schedule(self, job_id: str) -> None:
        """Compute and store the next run time after a job completes."""
        row = self._conn.execute(
            "SELECT schedule FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return
        nrt = next_run_time(row[0]).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE job_schedule SET next_run_at = ?, last_run_at = ? WHERE job_id = ?",
            (nrt, now, job_id),
        )
        self._conn.commit()

    def get_schedule_info(self, job_id: str) -> dict[str, Any] | None:
        """Return scheduling state for a job."""
        row = self._conn.execute(
            "SELECT next_run_at, last_run_at, last_status FROM job_schedule WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return {"next_run_at": row[0], "last_run_at": row[1], "last_status": row[2]}

    # ------------------------------------------------------------------
    # Run history
    # ------------------------------------------------------------------

    def record_run_start(self, job_id: str, run_id: str) -> None:
        """Record that a job run has started."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO job_runs (id, job_id, status, started_at) VALUES (?, ?, 'running', ?)",
            (run_id, job_id, now),
        )
        self._conn.execute(
            "UPDATE job_schedule SET last_status = 'running' WHERE job_id = ?",
            (job_id,),
        )
        self._conn.commit()

    def record_run_end(
        self,
        job_id: str,
        run_id: str,
        *,
        status: str,
        output_path: str | None = None,
        error: str | None = None,
        stats: dict[str, Any] | None = None,
    ) -> None:
        """Record that a job run has finished."""
        now = datetime.now(timezone.utc).isoformat()
        stats_json = json.dumps(stats) if stats else None
        self._conn.execute(
            """UPDATE job_runs
               SET status = ?, finished_at = ?, output_path = ?, error = ?, stats_json = ?
               WHERE id = ?
            """,
            (status, now, output_path, error, stats_json, run_id),
        )
        self._conn.execute(
            "UPDATE job_schedule SET last_status = ? WHERE job_id = ?",
            (status, job_id),
        )
        self._conn.commit()

    def get_runs(self, job_id: str, limit: int = 20) -> list[JobRunResult]:
        """List recent runs for a job, newest first."""
        rows = self._conn.execute(
            """SELECT id, job_id, status, started_at, finished_at, output_path, error, stats_json
               FROM job_runs WHERE job_id = ?
               ORDER BY started_at DESC LIMIT ?
            """,
            (job_id, limit),
        ).fetchall()
        return [
            JobRunResult(
                run_id=r[0], job_id=r[1], status=r[2],
                started_at=r[3] or "", finished_at=r[4] or "",
                output_path=r[5], error=r[6],
                stats=json.loads(r[7]) if r[7] else {},
            )
            for r in rows
        ]

    def get_run(self, run_id: str) -> JobRunResult | None:
        """Fetch a single run by ID."""
        row = self._conn.execute(
            """SELECT id, job_id, status, started_at, finished_at, output_path, error, stats_json
               FROM job_runs WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return JobRunResult(
            run_id=row[0], job_id=row[1], status=row[2],
            started_at=row[3] or "", finished_at=row[4] or "",
            output_path=row[5], error=row[6],
            stats=json.loads(row[7]) if row[7] else {},
        )

    # ------------------------------------------------------------------
    # Seed file loading
    # ------------------------------------------------------------------

    def load_seed_file(self, seed_path: str | Path) -> dict[str, list[str]]:
        """Sync job definitions from a YAML seed file.

        - Jobs in the file but not in DB → created (origin='seed')
        - Jobs in DB with origin='seed' but not in the file → deleted
        - Jobs created via API/voice (origin!='seed') → never touched

        Returns ``{"created": [...], "deleted": [...]}``.
        """
        import yaml

        path = Path(seed_path).expanduser().resolve()
        if not path.exists():
            # No seed file — delete all seed-origin jobs (file was removed)
            removed = self._delete_seed_jobs_not_in(set())
            return {"created": [], "deleted": removed}

        with open(path) as f:
            definitions = yaml.safe_load(f)

        if definitions is None:
            # Empty file — treat as "no seed jobs desired"
            definitions = {}
        elif not isinstance(definitions, dict):
            logger.warning("Seed file %s is not a YAML mapping — skipping", path)
            return {"created": [], "deleted": []}

        # Pass 1: upsert jobs from the file
        seed_names: set[str] = set()
        created: list[str] = []
        for name, raw in definitions.items():
            if not isinstance(raw, dict):
                continue

            if not raw.get("prompt") or not raw.get("schedule"):
                logger.warning("Seed job '%s' missing prompt or schedule — skipping", name)
                continue

            schedule = raw["schedule"]
            if not validate_cron(schedule):
                logger.warning("Seed job '%s' has invalid cron '%s' — skipping", name, schedule)
                continue

            seed_names.add(name)

            existing = self.get_job_by_name(name)
            if existing is not None:
                # Adopt: if this job exists but isn't tagged as seed, tag it now
                self._ensure_seed_origin(existing.id)
                continue  # Don't overwrite content

            raw["name"] = name
            job = JobDefinition.from_dict(raw)
            self.save_job(job, origin="seed")
            created.append(name)
            logger.info("Loaded seed job: %s (schedule=%s)", name, schedule)

        # Pass 2: delete seed-origin jobs not in the file
        deleted = self._delete_seed_jobs_not_in(seed_names)

        return {"created": created, "deleted": deleted}

    def _delete_seed_jobs_not_in(self, keep_names: set[str]) -> list[str]:
        """Delete jobs with origin='seed' whose name is not in *keep_names*."""
        rows = self._conn.execute(
            "SELECT id, name FROM jobs WHERE origin = 'seed'"
        ).fetchall()
        deleted: list[str] = []
        for job_id, name in rows:
            if name not in keep_names:
                self.delete_job(job_id)
                deleted.append(name)
                logger.info("Removed seed job no longer in file: %s", name)
        return deleted

    def _ensure_seed_origin(self, job_id: str) -> None:
        """Tag a job as seed-origin if it isn't already."""
        self._conn.execute(
            "UPDATE jobs SET origin = 'seed' WHERE id = ? AND origin != 'seed'",
            (job_id,),
        )
        self._conn.commit()

    def _migrate_origin_column(self) -> None:
        """Add origin column if missing (upgrade from pre-origin schema).

        Pre-existing jobs were all created from the seed file (the API/voice
        path didn't exist before this feature), so default to 'seed'.
        """
        cursor = self._conn.execute("PRAGMA table_info(jobs)")
        columns = {row[1] for row in cursor.fetchall()}
        if "origin" not in columns:
            self._conn.execute(
                "ALTER TABLE jobs ADD COLUMN origin TEXT NOT NULL DEFAULT 'seed'"
            )
            self._conn.commit()
            logger.info("Migrated jobs table: added origin column (default='seed')")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
