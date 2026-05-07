"""Tests for jobs/store.py — SQLite job persistence."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from tank_backend.jobs.models import JobDefinition
from tank_backend.jobs.store import JobStore
from tank_backend.persistence import Base, Database
from tank_backend.persistence.models import JobRow


@pytest.fixture()
def store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    s = JobStore(db)
    yield s
    s.close()
    db.dispose()


def _make_job(
    name: str = "test_job", schedule: str = "0 9 * * *", **kwargs,
) -> JobDefinition:
    return JobDefinition.from_dict({
        "name": name, "prompt": "Do something",
        "schedule": schedule, **kwargs,
    })


class TestJobCRUD:
    def test_save_and_get(self, store: JobStore):
        job = _make_job()
        store.save_job(job)
        fetched = store.get_job(job.id)
        assert fetched is not None
        assert fetched.name == "test_job"
        assert fetched.prompt == "Do something"

    def test_get_by_name(self, store: JobStore):
        job = _make_job("my_job")
        store.save_job(job)
        fetched = store.get_job_by_name("my_job")
        assert fetched is not None
        assert fetched.id == job.id

    def test_get_nonexistent(self, store: JobStore):
        assert store.get_job("nonexistent") is None
        assert store.get_job_by_name("nonexistent") is None

    def test_list_jobs(self, store: JobStore):
        store.save_job(_make_job("a"))
        store.save_job(_make_job("b"))
        jobs = store.list_jobs()
        assert len(jobs) == 2
        assert [j.name for j in jobs] == ["a", "b"]  # sorted by name

    def test_list_enabled_only(self, store: JobStore):
        store.save_job(_make_job("enabled_job", enabled=True))
        store.save_job(_make_job("disabled_job", enabled=False))
        enabled = store.list_jobs(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].name == "enabled_job"

    def test_delete(self, store: JobStore):
        job = _make_job()
        store.save_job(job)
        assert store.delete_job(job.id) is True
        assert store.get_job(job.id) is None

    def test_delete_nonexistent(self, store: JobStore):
        assert store.delete_job("nonexistent") is False

    def test_set_enabled(self, store: JobStore):
        job = _make_job()
        store.save_job(job)
        assert store.set_enabled(job.id, False) is True
        fetched = store.get_job(job.id)
        assert fetched is not None
        assert fetched.enabled is False

    def test_set_enabled_nonexistent(self, store: JobStore):
        assert store.set_enabled("nonexistent", True) is False

    def test_update_via_save(self, store: JobStore):
        job = _make_job()
        store.save_job(job)
        updated = JobDefinition.from_dict({**job.to_dict(), "prompt": "Updated prompt"})
        store.save_job(updated)
        fetched = store.get_job(job.id)
        assert fetched is not None
        assert fetched.prompt == "Updated prompt"


class TestRunHistory:
    def test_record_and_get_runs(self, store: JobStore):
        job = _make_job()
        store.save_job(job)
        store.record_run_start(job.id, "run1")
        store.record_run_end(job.id, "run1", status="succeeded", output_path="/tmp/out.md")

        runs = store.get_runs(job.id)
        assert len(runs) == 1
        assert runs[0].run_id == "run1"
        assert runs[0].status == "succeeded"
        assert runs[0].output_path == "/tmp/out.md"

    def test_get_single_run(self, store: JobStore):
        job = _make_job()
        store.save_job(job)
        store.record_run_start(job.id, "run1")
        store.record_run_end(job.id, "run1", status="failed", error="timeout")

        run = store.get_run("run1")
        assert run is not None
        assert run.status == "failed"
        assert run.error == "timeout"

    def test_cascade_delete(self, store: JobStore):
        job = _make_job()
        store.save_job(job)
        store.record_run_start(job.id, "run1")
        store.record_run_end(job.id, "run1", status="succeeded")
        store.delete_job(job.id)
        assert store.get_run("run1") is None


class TestSeedFile:
    def test_load_seed(self, store: JobStore, tmp_path):
        seed = tmp_path / "seed.yaml"
        seed.write_text(
            "morning_news:\n"
            "  prompt: Search for AI news\n"
            "  schedule: '0 9 * * *'\n"
            "  delivery:\n"
            "    channels:\n"
            "      - briefing\n"
        )
        result = store.load_seed_file(seed)
        assert result["created"] == ["morning_news"]
        assert result["deleted"] == []
        job = store.get_job_by_name("morning_news")
        assert job is not None
        assert job.delivery.channels == ("briefing",)

    def test_seed_idempotent(self, store: JobStore, tmp_path):
        seed = tmp_path / "seed.yaml"
        seed.write_text(
            "test_job:\n"
            "  prompt: Do something\n"
            "  schedule: '0 0 * * *'\n"
        )
        store.load_seed_file(seed)
        result = store.load_seed_file(seed)  # second load
        assert result["created"] == []
        assert result["deleted"] == []

    def test_seed_missing_file(self, store: JobStore, tmp_path):
        result = store.load_seed_file(tmp_path / "nonexistent.yaml")
        assert result["created"] == []
        assert result["deleted"] == []

    def test_seed_invalid_cron(self, store: JobStore, tmp_path):
        seed = tmp_path / "seed.yaml"
        seed.write_text(
            "bad_job:\n"
            "  prompt: Test\n"
            "  schedule: 'not valid'\n"
        )
        result = store.load_seed_file(seed)
        assert result["created"] == []

    def test_seed_sync_deletes_removed_jobs(self, store: JobStore, tmp_path):
        """Jobs removed from seed.yaml get deleted from DB."""
        seed = tmp_path / "seed.yaml"
        seed.write_text(
            "job_a:\n"
            "  prompt: A\n"
            "  schedule: '0 9 * * *'\n"
            "job_b:\n"
            "  prompt: B\n"
            "  schedule: '0 10 * * *'\n"
        )
        result = store.load_seed_file(seed)
        assert sorted(result["created"]) == ["job_a", "job_b"]

        # Remove job_b from seed
        seed.write_text(
            "job_a:\n"
            "  prompt: A\n"
            "  schedule: '0 9 * * *'\n"
        )
        result = store.load_seed_file(seed)
        assert result["created"] == []
        assert result["deleted"] == ["job_b"]
        assert store.get_job_by_name("job_b") is None
        assert store.get_job_by_name("job_a") is not None

    def test_seed_sync_does_not_delete_api_jobs(self, store: JobStore, tmp_path):
        """Jobs created via API/voice are never deleted by seed sync."""
        # Create a job via API (origin='api')
        api_job = _make_job("api_created")
        store.save_job(api_job, origin="api")

        # Load a seed file that doesn't mention api_created
        seed = tmp_path / "seed.yaml"
        seed.write_text(
            "seed_job:\n"
            "  prompt: From seed\n"
            "  schedule: '0 9 * * *'\n"
        )
        result = store.load_seed_file(seed)
        assert result["created"] == ["seed_job"]
        assert result["deleted"] == []
        # API job untouched
        assert store.get_job_by_name("api_created") is not None

    def test_seed_file_removed_deletes_all_seed_jobs(self, store: JobStore, tmp_path):
        """If seed file is deleted, all seed-origin jobs are removed."""
        seed = tmp_path / "seed.yaml"
        seed.write_text(
            "seed_job:\n"
            "  prompt: Test\n"
            "  schedule: '0 0 * * *'\n"
        )
        store.load_seed_file(seed)
        assert store.get_job_by_name("seed_job") is not None

        # Also create an API job
        api_job = _make_job("api_job")
        store.save_job(api_job, origin="api")

        # "Delete" the seed file by pointing to nonexistent path
        result = store.load_seed_file(tmp_path / "gone.yaml")
        assert result["deleted"] == ["seed_job"]
        assert store.get_job_by_name("seed_job") is None
        # API job survives
        assert store.get_job_by_name("api_job") is not None

    def test_seed_adopts_preexisting_api_job(self, store: JobStore, tmp_path):
        """A job created before seed sync gets adopted when it appears in seed."""
        # Simulate pre-existing job (origin='api', like after migration)
        job = _make_job("legacy_job")
        store.save_job(job, origin="api")

        # Seed file mentions the same name
        seed = tmp_path / "seed.yaml"
        seed.write_text(
            "legacy_job:\n"
            "  prompt: From seed\n"
            "  schedule: '0 9 * * *'\n"
        )
        result = store.load_seed_file(seed)
        assert result["created"] == []  # not re-created, just adopted

        # Verify origin was updated to 'seed' via the ORM layer
        with store._db.session() as s:
            origin = s.execute(
                select(JobRow.origin).where(JobRow.name == "legacy_job")
            ).scalar_one()
        assert origin == "seed"

        # Now remove from seed — should be deleted
        seed.write_text("")
        result = store.load_seed_file(seed)
        assert result["deleted"] == ["legacy_job"]
        assert store.get_job_by_name("legacy_job") is None
