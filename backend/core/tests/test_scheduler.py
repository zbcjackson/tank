"""Tests for jobs/scheduler.py — APScheduler-backed cron scheduling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.jobs.models import JobDefinition, JobRunResult
from tank_backend.jobs.scheduler import CronScheduler


def _make_job(name: str = "test_job", job_id: str = "j1") -> JobDefinition:
    return JobDefinition.from_dict({
        "id": job_id,
        "name": name,
        "prompt": "Do something",
        "schedule": "0 9 * * *",
    })


class TestCronScheduler:
    @pytest.fixture()
    def mock_store(self):
        store = MagicMock()
        store.list_jobs.return_value = []
        store.get_job.return_value = None
        return store

    @pytest.fixture()
    def mock_runner(self):
        runner = AsyncMock()
        runner.execute = AsyncMock(return_value=JobRunResult(
            run_id="r1", job_id="j1", status="succeeded",
        ))
        return runner

    async def test_start_stop(self, mock_store, mock_runner):
        scheduler = CronScheduler(mock_store, mock_runner)
        await scheduler.start()
        assert scheduler.status["running"] is True
        await scheduler.stop()
        assert scheduler.status["running"] is False

    async def test_trigger_job(self, mock_store, mock_runner):
        job = _make_job()
        mock_store.get_job.return_value = job

        scheduler = CronScheduler(mock_store, mock_runner)
        result = await scheduler.trigger_job(job.id)
        assert result is not None

        await asyncio.sleep(0.1)
        mock_runner.execute.assert_called_once_with(job)
        await scheduler.stop()

    async def test_trigger_nonexistent_job(self, mock_store, mock_runner):
        mock_store.get_job.return_value = None
        scheduler = CronScheduler(mock_store, mock_runner)
        result = await scheduler.trigger_job("nonexistent")
        assert result is None

    async def test_trigger_already_running(self, mock_store, mock_runner):
        job = _make_job()
        mock_store.get_job.return_value = job

        async def slow_execute(j):
            await asyncio.sleep(10)
            return JobRunResult(run_id="r", job_id=j.id, status="succeeded")

        mock_runner.execute = slow_execute

        scheduler = CronScheduler(mock_store, mock_runner)
        result1 = await scheduler.trigger_job(job.id)
        assert result1 is not None

        result2 = await scheduler.trigger_job(job.id)
        assert result2 is None  # already running

        await scheduler.stop()

    async def test_cancel_job(self, mock_store, mock_runner):
        job = _make_job()
        mock_store.get_job.return_value = job

        async def slow_execute(j):
            await asyncio.sleep(10)
            return JobRunResult(run_id="r", job_id=j.id, status="succeeded")

        mock_runner.execute = slow_execute

        scheduler = CronScheduler(mock_store, mock_runner)
        await scheduler.trigger_job(job.id)
        assert scheduler.status["active_jobs"] == 1

        cancelled = await scheduler.cancel_job(job.id)
        assert cancelled is True
        assert scheduler.status["active_jobs"] == 0

        await scheduler.stop()

    async def test_cancel_nonexistent(self, mock_store, mock_runner):
        scheduler = CronScheduler(mock_store, mock_runner)
        cancelled = await scheduler.cancel_job("nonexistent")
        assert cancelled is False

    async def test_status(self, mock_store, mock_runner):
        scheduler = CronScheduler(mock_store, mock_runner, max_parallel=5)
        s = scheduler.status
        assert s["running"] is False
        assert s["active_jobs"] == 0
        assert s["max_parallel"] == 5

    async def test_reload_seed(self, mock_store, mock_runner):
        mock_store.load_seed_file.return_value = {
            "created": ["new_job"],
            "deleted": [],
        }
        scheduler = CronScheduler(mock_store, mock_runner)
        result = scheduler.reload_seed("/tmp/seed.yaml")
        assert result["created"] == ["new_job"]
        mock_store.load_seed_file.assert_called_once_with("/tmp/seed.yaml")

    async def test_sync_schedules_on_start(self, mock_store, mock_runner):
        """Verify that start() syncs schedules from the job store."""
        job = _make_job()
        mock_store.list_jobs.return_value = [job]

        scheduler = CronScheduler(mock_store, mock_runner)
        await scheduler.start()

        # APScheduler should have a schedule registered
        schedules = await scheduler._scheduler.get_schedules()
        assert len(schedules) == 1
        assert schedules[0].id == f"tank_job_{job.id}"

        await scheduler.stop()
