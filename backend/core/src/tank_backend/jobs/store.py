"""SQLite-backed job store — definitions and run history.

Persists to the unified Tank database via the shared ORM layer. All
data lives in the ``jobs`` and ``job_runs`` tables managed by Alembic.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update

from ..persistence import Database
from ..persistence.models import JobRow, JobRunRow
from .cron import validate_cron
from .models import JobDefinition, JobRunResult

logger = logging.getLogger(__name__)


class JobStore:
    """Persistent store for job definitions and run history."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Job CRUD
    # ------------------------------------------------------------------

    def save_job(self, job: JobDefinition, origin: str = "api") -> None:
        """Insert or update a job definition."""
        now = datetime.now(timezone.utc).isoformat()
        config_json = job.to_json()
        with self._db.session() as s:
            existing = s.get(JobRow, job.id)
            if existing is None:
                s.add(JobRow(
                    id=job.id,
                    name=job.name,
                    prompt=job.prompt,
                    schedule=job.schedule,
                    enabled=int(job.enabled),
                    origin=origin,
                    config_json=config_json,
                    created_at=job.created_at or now,
                    updated_at=now,
                ))
            else:
                existing.name = job.name
                existing.prompt = job.prompt
                existing.schedule = job.schedule
                existing.enabled = int(job.enabled)
                existing.config_json = config_json
                existing.updated_at = now

    def get_job(self, job_id: str) -> JobDefinition | None:
        """Fetch a job by ID."""
        with self._db.session() as s:
            row = s.get(JobRow, job_id)
            if row is None:
                return None
            return JobDefinition.from_json(row.config_json)

    def get_job_by_name(self, name: str) -> JobDefinition | None:
        """Fetch a job by its human-readable name."""
        with self._db.session() as s:
            row = s.execute(
                select(JobRow).where(JobRow.name == name)
            ).scalar_one_or_none()
            if row is None:
                return None
            return JobDefinition.from_json(row.config_json)

    def list_jobs(self, enabled_only: bool = False) -> list[JobDefinition]:
        """List all jobs, optionally filtering to enabled only."""
        with self._db.session() as s:
            stmt = select(JobRow)
            if enabled_only:
                stmt = stmt.where(JobRow.enabled == 1)
            stmt = stmt.order_by(JobRow.name)
            rows = s.execute(stmt).scalars().all()
            return [JobDefinition.from_json(r.config_json) for r in rows]

    def delete_job(self, job_id: str) -> bool:
        """Delete a job and its run history. Returns True if found."""
        with self._db.session() as s:
            existing = s.get(JobRow, job_id)
            if existing is None:
                return False
            s.delete(existing)
        return True

    def set_enabled(self, job_id: str, enabled: bool) -> bool:
        """Enable or disable a job. Returns True if found."""
        now = datetime.now(timezone.utc).isoformat()
        with self._db.session() as s:
            row = s.get(JobRow, job_id)
            if row is None:
                return False
            row.enabled = int(enabled)
            row.updated_at = now
            # Keep config_json in sync so JobDefinition round-trips.
            data = json.loads(row.config_json)
            data["enabled"] = enabled
            data["updated_at"] = now
            row.config_json = json.dumps(data)
            return True

    # ------------------------------------------------------------------
    # Run history
    # ------------------------------------------------------------------

    def record_run_start(self, job_id: str, run_id: str) -> None:
        """Record that a job run has started."""
        now = datetime.now(timezone.utc).isoformat()
        with self._db.session() as s:
            s.add(JobRunRow(
                id=run_id,
                job_id=job_id,
                status="running",
                started_at=now,
            ))

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
        with self._db.session() as s:
            s.execute(
                update(JobRunRow)
                .where(JobRunRow.id == run_id)
                .values(
                    status=status,
                    finished_at=now,
                    output_path=output_path,
                    error=error,
                    stats_json=stats_json,
                )
            )

    def get_runs(self, job_id: str, limit: int = 20) -> list[JobRunResult]:
        """List recent runs for a job, newest first."""
        with self._db.session() as s:
            rows = s.execute(
                select(JobRunRow)
                .where(JobRunRow.job_id == job_id)
                .order_by(JobRunRow.started_at.desc())
                .limit(limit)
            ).scalars().all()
            return [_row_to_result(r) for r in rows]

    def get_run(self, run_id: str) -> JobRunResult | None:
        """Fetch a single run by ID."""
        with self._db.session() as s:
            row = s.get(JobRunRow, run_id)
            if row is None:
                return None
            return _row_to_result(row)

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
            removed = self._delete_seed_jobs_not_in(set())
            return {"created": [], "deleted": removed}

        with open(path) as f:
            definitions = yaml.safe_load(f)

        if definitions is None:
            definitions = {}
        elif not isinstance(definitions, dict):
            logger.warning("Seed file %s is not a YAML mapping — skipping", path)
            return {"created": [], "deleted": []}

        seed_names: set[str] = set()
        created: list[str] = []
        for name, raw in definitions.items():
            if not isinstance(raw, dict):
                continue
            if not raw.get("prompt") or not raw.get("schedule"):
                logger.warning(
                    "Seed job '%s' missing prompt or schedule — skipping", name,
                )
                continue
            schedule = raw["schedule"]
            if not validate_cron(schedule):
                logger.warning(
                    "Seed job '%s' has invalid cron '%s' — skipping",
                    name, schedule,
                )
                continue

            seed_names.add(name)

            existing = self.get_job_by_name(name)
            if existing is not None:
                self._ensure_seed_origin(existing.id)
                continue  # Don't overwrite content

            raw["name"] = name
            job = JobDefinition.from_dict(raw)
            self.save_job(job, origin="seed")
            created.append(name)
            logger.info("Loaded seed job: %s (schedule=%s)", name, schedule)

        deleted = self._delete_seed_jobs_not_in(seed_names)
        return {"created": created, "deleted": deleted}

    # ------------------------------------------------------------------
    # Helpers used by seed sync
    # ------------------------------------------------------------------

    def _delete_seed_jobs_not_in(self, keep_names: set[str]) -> list[str]:
        """Delete jobs with origin='seed' whose name is not in ``keep_names``."""
        with self._db.session() as s:
            rows = s.execute(
                select(JobRow.id, JobRow.name).where(JobRow.origin == "seed")
            ).all()
            to_delete = [(jid, name) for jid, name in rows if name not in keep_names]
            if to_delete:
                s.execute(
                    delete(JobRow).where(JobRow.id.in_([jid for jid, _ in to_delete]))
                )
        for _, name in to_delete:
            logger.info("Removed seed job no longer in file: %s", name)
        return [name for _, name in to_delete]

    def _ensure_seed_origin(self, job_id: str) -> None:
        """Tag a job as seed-origin if it isn't already."""
        with self._db.session() as s:
            s.execute(
                update(JobRow)
                .where((JobRow.id == job_id) & (JobRow.origin != "seed"))
                .values(origin="seed")
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """No-op: the Database owns the engine lifecycle."""
        return


def _row_to_result(row: JobRunRow) -> JobRunResult:
    return JobRunResult(
        run_id=row.id,
        job_id=row.job_id,
        status=row.status,
        started_at=row.started_at or "",
        finished_at=row.finished_at or "",
        output_path=row.output_path,
        error=row.error,
        stats=json.loads(row.stats_json) if row.stats_json else {},
    )
