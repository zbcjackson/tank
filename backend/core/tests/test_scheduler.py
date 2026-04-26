"""Tests for jobs/scheduler.py — cron tick loop and job launching."""

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
        store.get_due_jobs.return_value = []
        store.get_job.return_value = None
        store.advance_schedule = MagicMock()
        return store

    @pytest.fixture()
    def mock_runner(self):
        runner = AsyncMock()
        runner.execute = AsyncMock(return_value=JobRunResult(
            run_id="r1", job_id="j1", status="succeeded",
        ))
        return runner

    async def test_start_stop(self, mock_store, mock_runner):
        scheduler = CronScheduler(mock_store, mock_runner, tick_interval=0.05)
        await scheduler.start()
        assert scheduler.status["running"] is True
        await asyncio.sleep(0.1)
        await scheduler.stop()
        assert scheduler.status["running"] is False

    async def test_tick_launches_due_jobs(self, mock_store, mock_runner):
        job = _make_job()
        mock_store.get_due_jobs.return_value = [job]

        scheduler = CronScheduler(mock_store, mock_runner, tick_interval=100)
        # Call _tick directly instead of running the loop
        await scheduler._tick()

        # Wait for the launched task to complete
        await asyncio.sleep(0.1)

        mock_runner.execute.assert_called_once_with(job)
        mock_store.advance_schedule.assert_called_once_with(job.id)

    async def test_tick_respects_max_parallel(self, mock_store, mock_runner):
        jobs = [_make_job(f"job_{i}", f"j{i}") for i in range(5)]
        mock_store.get_due_jobs.return_value = jobs

        # Make runner slow so jobs stay "running"
        async def slow_execute(job):
            await asyncio.sleep(10)
            return JobRunResult(run_id="r", job_id=job.id, status="succeeded")

        mock_runner.execute = slow_execute

        scheduler = CronScheduler(mock_store, mock_runner, max_parallel=2, tick_interval=100)
        await scheduler._tick()

        assert scheduler.status["active_jobs"] == 2

        # Cleanup
        await scheduler.stop()

    async def test_tick_skips_already_running(self, mock_store, mock_runner):
        job = _make_job()
        mock_store.get_due_jobs.return_value = [job]

        async def slow_execute(j):
            await asyncio.sleep(10)
            return JobRunResult(run_id="r", job_id=j.id, status="succeeded")

        mock_runner.execute = slow_execute

        scheduler = CronScheduler(mock_store, mock_runner, tick_interval=100)
        await scheduler._tick()  # launches job
        await scheduler._tick()  # should skip (already running)

        assert scheduler.status["active_jobs"] == 1
        await scheduler.stop()

    async def test_trigger_job(self, mock_store, mock_runner):
        job = _make_job()
        mock_store.get_job.return_value = job

        scheduler = CronScheduler(mock_store, mock_runner, tick_interval=100)
        result = await scheduler.trigger_job(job.id)
        assert result is not None

        await asyncio.sleep(0.1)
        mock_runner.execute.assert_called_once_with(job)
        await scheduler.stop()

    async def test_trigger_nonexistent_job(self, mock_store, mock_runner):
        mock_store.get_job.return_value = None
        scheduler = CronScheduler(mock_store, mock_runner, tick_interval=100)
        result = await scheduler.trigger_job("nonexistent")
        assert result is None

    async def test_trigger_at_capacity(self, mock_store, mock_runner):
        jobs = [_make_job(f"job_{i}", f"j{i}") for i in range(3)]
        mock_store.get_due_jobs.return_value = jobs

        async def slow_execute(j):
            await asyncio.sleep(10)
            return JobRunResult(run_id="r", job_id=j.id, status="succeeded")

        mock_runner.execute = slow_execute

        scheduler = CronScheduler(mock_store, mock_runner, max_parallel=3, tick_interval=100)
        await scheduler._tick()  # fills all 3 slots

        new_job = _make_job("extra", "j_extra")
        mock_store.get_job.return_value = new_job
        result = await scheduler.trigger_job(new_job.id)
        assert result is None  # at capacity

        await scheduler.stop()

    async def test_status(self, mock_store, mock_runner):
        scheduler = CronScheduler(mock_store, mock_runner, max_parallel=5, tick_interval=100)
        s = scheduler.status
        assert s["running"] is False
        assert s["active_jobs"] == 0
        assert s["max_parallel"] == 5

    async def test_cleanup_finished_tasks(self, mock_store, mock_runner):
        job = _make_job()
        mock_store.get_due_jobs.return_value = [job]

        scheduler = CronScheduler(mock_store, mock_runner, tick_interval=100)
        await scheduler._tick()
        await asyncio.sleep(0.1)  # let the task finish

        scheduler._cleanup_finished()
        assert scheduler.status["active_jobs"] == 0
