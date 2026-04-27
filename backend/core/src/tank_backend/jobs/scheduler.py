"""Cron scheduler — APScheduler-backed job scheduling and execution."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from apscheduler import AsyncScheduler, ConflictPolicy
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from .models import JobDefinition
    from .runner import AutonomousRunner
    from .store import JobStore

logger = logging.getLogger(__name__)


class CronScheduler:
    """APScheduler-backed scheduler for autonomous jobs."""

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
        self._scheduler = AsyncScheduler(max_concurrent_jobs=max_parallel)
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._started = False

    async def start(self) -> None:
        """Initialize APScheduler, sync schedules, start background loop."""
        await self._scheduler.__aenter__()
        await self._sync_schedules()
        await self._scheduler.start_in_background()
        self._started = True
        logger.info(
            "CronScheduler started (APScheduler, max_parallel=%d)",
            self._max_parallel,
        )

    async def stop(self) -> None:
        """Stop scheduler and cancel running tasks."""
        if self._started:
            await self._scheduler.stop()
            await self._scheduler.__aexit__(None, None, None)
            self._started = False

        for task in self._running_tasks.values():
            task.cancel()
        if self._running_tasks:
            await asyncio.gather(
                *self._running_tasks.values(), return_exceptions=True,
            )
        self._running_tasks.clear()
        logger.info("CronScheduler stopped")

    async def trigger_job(self, job_id: str) -> str | None:
        """Manually trigger a job immediately. Returns job_id or None."""
        job = self._job_store.get_job(job_id)
        if job is None:
            logger.warning("trigger_job: job '%s' not found", job_id)
            return None

        if job.id in self._running_tasks:
            logger.warning("trigger_job: job '%s' already running", job.name)
            return None

        task = asyncio.create_task(self._execute_job(job))
        self._running_tasks[job.id] = task
        logger.info("Manually triggered job '%s'", job.name)
        return job.id

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job. Returns True if it was running."""
        task = self._running_tasks.pop(job_id, None)
        if task is None:
            return False
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        logger.info("Cancelled running job '%s'", job_id)
        return True

    def reload_seed(self, seed_path: str | None = None) -> dict[str, list[str]]:
        """Reload seed file — sync mode."""
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
        if self._started and (result["created"] or result["deleted"]):
            asyncio.create_task(self._sync_schedules())
        return result

    @property
    def status(self) -> dict[str, Any]:
        """Scheduler status for health/status endpoints."""
        self._cleanup_finished()
        return {
            "running": self._started,
            "active_jobs": len(self._running_tasks),
            "max_parallel": self._max_parallel,
            "active_job_ids": list(self._running_tasks.keys()),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _sync_schedules(self) -> None:
        """Sync APScheduler schedules with our JobStore definitions."""
        jobs = self._job_store.list_jobs(enabled_only=True)

        existing_schedules = await self._scheduler.get_schedules()
        existing_ids = {s.id for s in existing_schedules}

        desired_ids: set[str] = set()
        for job in jobs:
            schedule_id = f"tank_job_{job.id}"
            desired_ids.add(schedule_id)

            trigger = CronTrigger.from_crontab(job.schedule)
            await self._scheduler.add_schedule(
                self._on_schedule_fire,
                trigger,
                id=schedule_id,
                kwargs={"job_id": job.id},
                conflict_policy=ConflictPolicy.replace,
            )

        for schedule_id in existing_ids - desired_ids:
            if schedule_id.startswith("tank_job_"):
                with contextlib.suppress(Exception):
                    await self._scheduler.remove_schedule(schedule_id)

    async def _on_schedule_fire(self, job_id: str) -> None:
        """Called by APScheduler when a schedule fires."""
        job = self._job_store.get_job(job_id)
        if job is None or not job.enabled:
            return

        if job.id in self._running_tasks:
            logger.debug("Job '%s' already running, skipping", job.name)
            return

        task = asyncio.create_task(self._execute_job(job))
        self._running_tasks[job.id] = task
        logger.info("Launched job '%s' (id=%s)", job.name, job.id[:8])

    async def _execute_job(self, job: JobDefinition) -> None:
        """Execute a single job and clean up."""
        try:
            await self._runner.execute(job)
        except asyncio.CancelledError:
            logger.info("Job '%s' cancelled", job.name)
        except Exception:
            logger.error(
                "Job '%s' failed unexpectedly", job.name, exc_info=True,
            )
        finally:
            self._running_tasks.pop(job.id, None)

    def _cleanup_finished(self) -> None:
        """Remove completed tasks from the running set."""
        finished = [
            jid for jid, task in self._running_tasks.items() if task.done()
        ]
        for jid in finished:
            self._running_tasks.pop(jid, None)
