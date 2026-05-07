"""Integration tests for the cron job system.

These tests cover the end-to-end flows that unit tests missed:
1. Job fires → runner executes → delivery saves output → run history recorded
2. Job timeout is enforced and recorded
3. Job failure is recorded with error
4. Seed sync creates/deletes jobs and syncs APScheduler
5. manage_jobs tool creates job and syncs APScheduler
6. Approval mode (always_approve/always_deny) affects tool execution
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.jobs.delivery import DeliveryManager
from tank_backend.jobs.models import JobDefinition
from tank_backend.jobs.runner import AutonomousRunner
from tank_backend.jobs.scheduler import CronScheduler
from tank_backend.jobs.store import JobStore
from tank_backend.persistence import Base, Database

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def job_store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    store = JobStore(db)
    yield store
    store.close()
    db.dispose()


@pytest.fixture()
def delivery(tmp_path):
    return DeliveryManager(output_dir=tmp_path / "output")


@pytest.fixture()
def app_config():
    """Minimal mock AppConfig for AutonomousRunner."""
    cfg = MagicMock()
    cfg.get_section.return_value = {}
    cfg.get_llm_profile.return_value = MagicMock(
        name="default", api_key="test", model="test-model",
        base_url="http://localhost", temperature=0.7,
        max_tokens=100, extra_headers={}, stream_options=False,
        extra_body=None,
    )
    return cfg


def _make_job(
    name: str = "test_job",
    schedule: str = "*/1 * * * *",
    **kwargs,
) -> JobDefinition:
    return JobDefinition.from_dict({
        "name": name,
        "prompt": "Say hello",
        "schedule": schedule,
        **kwargs,
    })


# ---------------------------------------------------------------------------
# 1. End-to-end: trigger → execute → deliver → history
# ---------------------------------------------------------------------------


class TestJobEndToEnd:
    """Full flow: scheduler triggers job → runner executes → output saved."""

    async def test_trigger_executes_and_records_history(
        self, job_store, delivery, tmp_path,
    ):
        """Triggering a job should execute it and record run history."""
        # Mock the agent execution to return a known result
        runner = AutonomousRunner(
            app_config=MagicMock(),
            job_store=job_store,
            delivery=delivery,
        )

        job = _make_job()
        job_store.save_job(job)

        # Patch _run_agent to avoid needing real LLM
        with patch.object(
            runner, "_run_agent", return_value="Hello from the job!",
        ):
            result = await runner.execute(job)

        assert result.status == "succeeded"
        assert result.output_path is not None

        # Verify output file was created
        output_path = Path(result.output_path)
        assert output_path.exists()
        content = output_path.read_text()
        assert "Hello from the job!" in content
        assert "test_job" in content

        # Verify run history was recorded
        runs = job_store.get_runs(job.id)
        assert len(runs) == 1
        assert runs[0].status == "succeeded"
        assert runs[0].output_path == str(output_path)

    async def test_trigger_via_scheduler_executes(
        self, job_store, delivery, tmp_path,
    ):
        """Scheduler.trigger_job() should execute the job end-to-end."""
        runner = AutonomousRunner(
            app_config=MagicMock(),
            job_store=job_store,
            delivery=delivery,
        )

        job = _make_job()
        job_store.save_job(job)

        scheduler = CronScheduler(job_store, runner)
        await scheduler.start()

        with patch.object(
            runner, "_run_agent", return_value="Triggered result",
        ):
            await scheduler.trigger_job(job.id)
            await asyncio.sleep(0.2)  # Let the task complete

        runs = job_store.get_runs(job.id)
        assert len(runs) == 1
        assert runs[0].status == "succeeded"

        await scheduler.stop()


# ---------------------------------------------------------------------------
# 2. Timeout enforcement
# ---------------------------------------------------------------------------


class TestJobTimeout:
    async def test_timeout_recorded(self, job_store, delivery):
        """Jobs that exceed timeout should be recorded as 'timeout'."""
        runner = AutonomousRunner(
            app_config=MagicMock(),
            job_store=job_store,
            delivery=delivery,
        )

        job = _make_job(timeout_seconds=1)
        job_store.save_job(job)

        # _run_agent contains the asyncio.timeout() wrapper, so we need
        # to raise TimeoutError directly to simulate what happens when
        # the timeout fires inside _run_agent.
        with patch.object(
            runner, "_run_agent", side_effect=asyncio.TimeoutError,
        ):
            result = await runner.execute(job)

        assert result.status == "timeout"
        assert "Exceeded 1s timeout" in (result.error or "")

        runs = job_store.get_runs(job.id)
        assert len(runs) == 1
        assert runs[0].status == "timeout"


# ---------------------------------------------------------------------------
# 3. Failure recording
# ---------------------------------------------------------------------------


class TestJobFailure:
    async def test_exception_recorded_as_failed(self, job_store, delivery):
        """Exceptions during execution should be recorded as 'failed'."""
        runner = AutonomousRunner(
            app_config=MagicMock(),
            job_store=job_store,
            delivery=delivery,
        )

        job = _make_job()
        job_store.save_job(job)

        with patch.object(
            runner, "_run_agent",
            side_effect=RuntimeError("LLM connection failed"),
        ):
            result = await runner.execute(job)

        assert result.status == "failed"
        assert "LLM connection failed" in (result.error or "")

        runs = job_store.get_runs(job.id)
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert "LLM connection failed" in (runs[0].error or "")


# ---------------------------------------------------------------------------
# 4. Seed sync + APScheduler integration
# ---------------------------------------------------------------------------


class TestSeedSyncIntegration:
    """Seed file changes sync to both DB and APScheduler."""

    async def test_seed_creates_job_and_registers_schedule(
        self, job_store, tmp_path,
    ):
        """Loading a seed file should create the job AND register it."""
        runner = AsyncMock()
        scheduler = CronScheduler(job_store, runner)
        await scheduler.start()

        seed = tmp_path / "seed.yaml"
        seed.write_text(
            "morning_news:\n"
            "  prompt: Get AI news\n"
            "  schedule: '0 9 * * *'\n"
        )
        result = scheduler.reload_seed(str(seed))
        assert result["created"] == ["morning_news"]

        # Wait for async sync
        await asyncio.sleep(0.1)

        # Verify APScheduler has the schedule
        job = job_store.get_job_by_name("morning_news")
        schedules = await scheduler._scheduler.get_schedules()
        ids = {s.id for s in schedules}
        assert f"tank_job_{job.id}" in ids

        await scheduler.stop()

    async def test_seed_removal_deletes_job_and_schedule(
        self, job_store, tmp_path,
    ):
        """Removing a job from seed should delete from DB AND APScheduler."""
        runner = AsyncMock()
        scheduler = CronScheduler(job_store, runner)
        await scheduler.start()

        # Create via seed
        seed = tmp_path / "seed.yaml"
        seed.write_text(
            "temp_job:\n"
            "  prompt: Temporary\n"
            "  schedule: '0 9 * * *'\n"
        )
        scheduler.reload_seed(str(seed))
        await asyncio.sleep(0.1)

        job = job_store.get_job_by_name("temp_job")
        assert job is not None

        # Remove from seed
        seed.write_text("")
        result = scheduler.reload_seed(str(seed))
        assert result["deleted"] == ["temp_job"]

        await asyncio.sleep(0.1)

        # Verify gone from both DB and APScheduler
        assert job_store.get_job_by_name("temp_job") is None
        schedules = await scheduler._scheduler.get_schedules()
        ids = {s.id for s in schedules}
        assert f"tank_job_{job.id}" not in ids

        await scheduler.stop()


# ---------------------------------------------------------------------------
# 5. manage_jobs tool → APScheduler sync
# ---------------------------------------------------------------------------


class TestManageJobsToolSync:
    """manage_jobs tool operations sync to APScheduler."""

    async def test_create_via_tool_registers_schedule(
        self, job_store, tmp_path,
    ):
        """Creating a job via manage_jobs should register it with APScheduler."""
        from tank_backend.tools.job_tools import JobManagementTool

        runner_mock = AsyncMock()
        scheduler = CronScheduler(job_store, runner_mock)
        await scheduler.start()

        tool = JobManagementTool(job_store, scheduler)
        result = await tool.execute(
            action="create",
            name="tool_created_job",
            prompt="Do something",
            schedule="0 9 * * *",
        )
        assert not result.error

        # Verify APScheduler has the schedule
        job = job_store.get_job_by_name("tool_created_job")
        schedules = await scheduler._scheduler.get_schedules()
        ids = {s.id for s in schedules}
        assert f"tank_job_{job.id}" in ids

        await scheduler.stop()

    async def test_delete_via_tool_removes_schedule(
        self, job_store, tmp_path,
    ):
        """Deleting a job via manage_jobs should remove from APScheduler."""
        from tank_backend.tools.job_tools import JobManagementTool

        runner_mock = AsyncMock()
        scheduler = CronScheduler(job_store, runner_mock)
        await scheduler.start()

        # Create first
        job = _make_job("to_delete")
        job_store.save_job(job)
        await scheduler.sync_schedules()

        tool = JobManagementTool(job_store, scheduler)
        result = await tool.execute(action="delete", name="to_delete")
        assert not result.error

        # Verify removed from APScheduler
        schedules = await scheduler._scheduler.get_schedules()
        ids = {s.id for s in schedules}
        assert f"tank_job_{job.id}" not in ids

        await scheduler.stop()

    async def test_disable_via_tool_removes_schedule(
        self, job_store, tmp_path,
    ):
        """Disabling a job via manage_jobs should remove its schedule."""
        from tank_backend.tools.job_tools import JobManagementTool

        runner_mock = AsyncMock()
        scheduler = CronScheduler(job_store, runner_mock)
        await scheduler.start()

        job = _make_job("to_disable")
        job_store.save_job(job)
        await scheduler.sync_schedules()

        # Verify it's scheduled
        schedules = await scheduler._scheduler.get_schedules()
        assert any(s.id == f"tank_job_{job.id}" for s in schedules)

        tool = JobManagementTool(job_store, scheduler)
        await tool.execute(action="disable", name="to_disable")

        # Verify removed
        schedules = await scheduler._scheduler.get_schedules()
        assert not any(s.id == f"tank_job_{job.id}" for s in schedules)

        await scheduler.stop()


# ---------------------------------------------------------------------------
# 6. Approval mode affects autonomous execution
# ---------------------------------------------------------------------------


class TestApprovalModeIntegration:
    """Verify approval_mode correctly configures the resolver."""

    async def test_always_deny_builds_deny_resolver(self, job_store, delivery):
        """always_deny should create AlwaysDenyResolver."""
        runner = AutonomousRunner(
            app_config=MagicMock(),
            job_store=job_store,
            delivery=delivery,
        )
        job = _make_job(approval_mode="always_deny")
        resolver = runner._build_resolver(job)

        from tank_backend.policy.verdict import (
            AccessLevel,
            AlwaysDenyResolver,
            PolicyVerdict,
        )

        assert isinstance(resolver, AlwaysDenyResolver)
        # Verify it denies
        v = PolicyVerdict(
            level=AccessLevel.REQUIRE_APPROVAL,
            reason="test", policy="command",
        )
        result = await resolver.resolve(v, "run_command", {})
        assert result == AccessLevel.DENY

    async def test_always_approve_builds_approve_resolver(
        self, job_store, delivery,
    ):
        """always_approve should create AlwaysApproveResolver."""
        runner = AutonomousRunner(
            app_config=MagicMock(),
            job_store=job_store,
            delivery=delivery,
        )
        job = _make_job(approval_mode="always_approve")
        resolver = runner._build_resolver(job)

        from tank_backend.policy.verdict import (
            AccessLevel,
            AlwaysApproveResolver,
            PolicyVerdict,
        )

        assert isinstance(resolver, AlwaysApproveResolver)
        # Verify it approves
        v = PolicyVerdict(
            level=AccessLevel.REQUIRE_APPROVAL,
            reason="test", policy="command",
        )
        result = await resolver.resolve(v, "run_command", {})
        assert result == AccessLevel.ALLOW
