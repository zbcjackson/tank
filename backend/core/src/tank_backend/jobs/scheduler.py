"""Cron scheduler — background asyncio task that ticks and launches due jobs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import JobDefinition
    from .runner import AutonomousRunner
    from .store import JobStore

logger = logging.getLogger(__name__)


class CronScheduler:
    """Tick-based scheduler that checks for due jobs every N seconds."""

    def __init__(
        self,
        job_store: JobStore,
        runner: AutonomousRunner,
        max_parallel: int = 3,
        tick_interval: float = 60.0,
    ) -> None:
        self._job_store = job_store
        self._runner = runner
        self._max_parallel = max_parallel
        self._tick_interval = tick_interval
        self._running_jobs: dict[str, asyncio.Task[None]] = {}
        self._tick_task: asyncio.Task[None] | None = None
        self._stopped = False

    async def start(self) -> None:
        """Start the scheduler tick loop."""
        self._stopped = False
        self._tick_task = asyncio.create_task(self._tick_loop())
        logger.info(
            "CronScheduler started (tick=%.0fs, max_parallel=%d)",
            self._tick_interval, self._max_parallel,
        )

    async def stop(self) -> None:
        """Stop scheduler and cancel all running jobs."""
        self._stopped = True
        if self._tick_task is not None:
            self._tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tick_task
            self._tick_task = None

        # Cancel running jobs
        for task in self._running_jobs.values():
            task.cancel()
        if self._running_jobs:
            await asyncio.gather(*self._running_jobs.values(), return_exceptions=True)
        self._running_jobs.clear()
        logger.info("CronScheduler stopped")

    async def trigger_job(self, job_id: str) -> str | None:
        """Manually trigger a job, bypassing schedule. Returns run_id or None."""
        job = self._job_store.get_job(job_id)
        if job is None:
            logger.warning("trigger_job: job '%s' not found", job_id)
            return None

        if job.id in self._running_jobs:
            logger.warning("trigger_job: job '%s' already running", job.name)
            return None

        if len(self._running_jobs) >= self._max_parallel:
            logger.warning(
                "trigger_job: at capacity (%d/%d)",
                len(self._running_jobs), self._max_parallel,
            )
            return None

        task = asyncio.create_task(self._run_job(job))
        self._running_jobs[job.id] = task
        logger.info("Manually triggered job '%s'", job.name)
        return job.id

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job. Returns True if it was running."""
        task = self._running_jobs.pop(job_id, None)
        if task is None:
            return False
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        logger.info("Cancelled running job '%s'", job_id)
        return True

    def reload_seed(self, seed_path: str | None = None) -> dict[str, list[str]]:
        """Reload seed file — sync mode. Returns {"created": [...], "deleted": [...]}."""
        path = seed_path or "~/.tank/jobs/seed.yaml"
        result = self._job_store.load_seed_file(path)
        if result["created"]:
            logger.info(
                "Seed reload: %d new: %s",
                len(result["created"]), ", ".join(result["created"]),
            )
        if result["deleted"]:
            logger.info(
                "Seed reload: %d removed: %s",
                len(result["deleted"]), ", ".join(result["deleted"]),
            )
        return result

    @property
    def status(self) -> dict[str, Any]:
        """Scheduler status for health/status endpoints."""
        return {
            "running": self._tick_task is not None and not self._tick_task.done(),
            "active_jobs": len(self._running_jobs),
            "max_parallel": self._max_parallel,
            "active_job_ids": list(self._running_jobs.keys()),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _tick_loop(self) -> None:
        while not self._stopped:
            try:
                await self._tick()
            except Exception:
                logger.error("Scheduler tick error", exc_info=True)
            await asyncio.sleep(self._tick_interval)

    async def _tick(self) -> None:
        """Find due jobs and launch them."""
        self._cleanup_finished()

        due_jobs = self._job_store.get_due_jobs()
        for job in due_jobs:
            if job.id in self._running_jobs:
                continue
            if len(self._running_jobs) >= self._max_parallel:
                logger.debug("Scheduler at capacity, deferring remaining due jobs")
                break
            task = asyncio.create_task(self._run_job(job))
            self._running_jobs[job.id] = task
            logger.info("Launched job '%s' (id=%s)", job.name, job.id[:8])

    async def _run_job(self, job: JobDefinition) -> None:
        """Execute a single job and advance its schedule."""
        try:
            await self._runner.execute(job)
        except asyncio.CancelledError:
            logger.info("Job '%s' cancelled", job.name)
        except Exception:
            logger.error("Job '%s' failed unexpectedly", job.name, exc_info=True)
        finally:
            self._running_jobs.pop(job.id, None)
            try:
                self._job_store.advance_schedule(job.id)
            except Exception:
                logger.error("Failed to advance schedule for '%s'", job.name, exc_info=True)

    def _cleanup_finished(self) -> None:
        """Remove completed tasks from the running set."""
        finished = [jid for jid, task in self._running_jobs.items() if task.done()]
        for jid in finished:
            self._running_jobs.pop(jid, None)
