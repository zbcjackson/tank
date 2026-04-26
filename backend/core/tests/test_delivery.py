"""Tests for jobs/delivery.py — text file and webhook delivery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tank_backend.jobs.delivery import DeliveryManager, _sanitize_dirname
from tank_backend.jobs.models import JobDefinition


def _make_job(name: str = "test_job", **delivery_kwargs) -> JobDefinition:
    return JobDefinition.from_dict({
        "name": name,
        "prompt": "Do something",
        "schedule": "0 9 * * *",
        "delivery": delivery_kwargs,
    })


class TestSanitizeDirname:
    def test_simple(self):
        assert _sanitize_dirname("morning_news") == "morning_news"

    def test_spaces_and_special(self):
        result = _sanitize_dirname("My Job! (v2)")
        assert " " not in result
        assert "!" not in result
        assert "(" not in result

    def test_truncation(self):
        long_name = "a" * 100
        assert len(_sanitize_dirname(long_name)) <= 64

    def test_empty(self):
        assert _sanitize_dirname("") == "unnamed"


class TestTextDelivery:
    @pytest.fixture()
    def manager(self, tmp_path):
        return DeliveryManager(output_dir=tmp_path / "output")

    async def test_save_text_default_path(self, manager, tmp_path):
        job = _make_job()
        path = await manager.deliver(job, "run123", "Hello world")
        assert path.endswith(".md")
        content = Path(path).read_text()
        assert "Hello world" in content
        assert "test_job" in content
        assert "run123" in content

    async def test_save_text_custom_path(self, manager, tmp_path):
        custom = str(tmp_path / "custom_output.md")
        job = _make_job(text_path=custom)
        path = await manager.deliver(job, "run456", "Custom output")
        assert path == custom
        content = Path(path).read_text()
        assert "Custom output" in content

    async def test_creates_directories(self, manager, tmp_path):
        job = _make_job(text_path=str(tmp_path / "deep" / "nested" / "out.md"))
        path = await manager.deliver(job, "run789", "Nested")
        assert Path(path).read_text().endswith("Nested")


class TestAudioDelivery:
    async def test_audio_queued(self, tmp_path):
        manager = DeliveryManager(output_dir=tmp_path / "output")
        job = _make_job(audio=True, audio_priority="normal")
        await manager.deliver(job, "run1", "News briefing text")

        queue = manager.drain_audio_queue()
        assert len(queue) == 1
        assert queue[0][0].name == "test_job"
        assert queue[0][1] == "News briefing text"

    async def test_drain_clears_queue(self, tmp_path):
        manager = DeliveryManager(output_dir=tmp_path / "output")
        job = _make_job(audio=True)
        await manager.deliver(job, "run1", "Text 1")
        await manager.deliver(job, "run2", "Text 2")

        queue = manager.drain_audio_queue()
        assert len(queue) == 2
        assert manager.drain_audio_queue() == []  # cleared

    async def test_no_audio_no_queue(self, tmp_path):
        manager = DeliveryManager(output_dir=tmp_path / "output")
        job = _make_job(audio=False)
        await manager.deliver(job, "run1", "Silent")
        assert manager.drain_audio_queue() == []


class TestWebhookDelivery:
    async def test_webhook_called(self, tmp_path):
        manager = DeliveryManager(output_dir=tmp_path / "output")
        job = _make_job(webhook_url="https://example.com/hook")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await manager.deliver(job, "run1", "Webhook payload")

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["json"]["job_name"] == "test_job"
        assert call_kwargs.kwargs["json"]["output"] == "Webhook payload"

    async def test_webhook_failure_does_not_raise(self, tmp_path):
        manager = DeliveryManager(output_dir=tmp_path / "output")
        job = _make_job(webhook_url="https://example.com/hook")

        with patch("httpx.AsyncClient", side_effect=Exception("connection refused")):
            # Should not raise — webhook failures are logged, not propagated
            path = await manager.deliver(job, "run1", "Text still saved")
            assert path.endswith(".md")
