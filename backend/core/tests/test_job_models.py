"""Tests for jobs/models.py — data model serialization and immutability."""

from __future__ import annotations

import pytest

from tank_backend.jobs.models import DeliveryConfig, JobDefinition, JobRunResult


class TestDeliveryConfig:
    def test_defaults(self):
        cfg = DeliveryConfig()
        assert cfg.audio is False
        assert cfg.text is True
        assert cfg.audio_priority == "low"
        assert cfg.audio_idle_threshold == 300
        assert cfg.webhook_headers == {}

    def test_roundtrip(self):
        cfg = DeliveryConfig(
            audio=True, audio_voice="en-US-JennyNeural",
            audio_priority="high", webhook_url="https://example.com/hook",
            webhook_headers={"X-Token": "abc"},
        )
        data = cfg.to_dict()
        restored = DeliveryConfig.from_dict(data)
        assert restored == cfg

    def test_from_dict_missing_keys(self):
        cfg = DeliveryConfig.from_dict({})
        assert cfg.audio is False
        assert cfg.text is True


class TestJobDefinition:
    def test_roundtrip(self):
        job = JobDefinition.from_dict({
            "name": "test_job",
            "prompt": "Do something",
            "schedule": "0 9 * * *",
            "allowed_tools": ["web_search", "web_fetch"],
            "delivery": {"audio": True},
        })
        assert job.name == "test_job"
        assert job.allowed_tools == ("web_search", "web_fetch")
        assert job.delivery.audio is True

        data = job.to_dict()
        restored = JobDefinition.from_dict(data)
        assert restored.name == job.name
        assert restored.prompt == job.prompt
        assert restored.allowed_tools == job.allowed_tools

    def test_json_roundtrip(self):
        job = JobDefinition.from_dict({
            "name": "json_test",
            "prompt": "Hello",
            "schedule": "*/5 * * * *",
        })
        json_str = job.to_json()
        restored = JobDefinition.from_json(json_str)
        assert restored.name == "json_test"
        assert restored.schedule == "*/5 * * * *"

    def test_frozen(self):
        job = JobDefinition.from_dict({
            "name": "frozen_test",
            "prompt": "Test",
            "schedule": "0 0 * * *",
        })
        with pytest.raises(AttributeError):
            job.name = "changed"  # type: ignore[misc]

    def test_defaults(self):
        job = JobDefinition.from_dict({
            "name": "defaults",
            "prompt": "Test",
            "schedule": "0 0 * * *",
        })
        assert job.enabled is True
        assert job.agent == "chat"
        assert job.max_iterations == 30
        assert job.timeout_seconds == 300
        assert job.approval_mode == "deny"
        assert job.allowed_tools is None
        assert job.blocked_tools is None

    def test_tuple_tools(self):
        job = JobDefinition.from_dict({
            "name": "tools",
            "prompt": "Test",
            "schedule": "0 0 * * *",
            "blocked_tools": ["run_command"],
        })
        assert isinstance(job.blocked_tools, tuple)
        assert job.blocked_tools == ("run_command",)


class TestJobRunResult:
    def test_roundtrip(self):
        result = JobRunResult(
            run_id="abc123", job_id="job1", status="succeeded",
            output_path="/tmp/out.md", stats={"duration_s": 5.2},
        )
        data = result.to_dict()
        restored = JobRunResult.from_dict(data)
        assert restored.run_id == "abc123"
        assert restored.status == "succeeded"
        assert restored.stats == {"duration_s": 5.2}

    def test_defaults(self):
        result = JobRunResult.from_dict({
            "run_id": "r1", "job_id": "j1", "status": "pending",
        })
        assert result.started_at == ""
        assert result.output_path is None
        assert result.error is None
        assert result.stats == {}
