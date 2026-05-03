"""Tests for jobs/delivery.py — channel and file log delivery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

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

    async def test_save_text_log_output_enabled(self, manager, tmp_path):
        job = _make_job(log_output=True)
        path = await manager.deliver(job, "run123", "Hello world")
        assert path.endswith(".md")
        content = Path(path).read_text()
        assert "Hello world" in content
        assert "test_job" in content
        assert "run123" in content

    async def test_no_file_when_log_output_disabled(self, manager, tmp_path):
        job = _make_job(log_output=False)
        path = await manager.deliver(job, "run456", "No file")
        assert path == ""

    async def test_creates_directories(self, manager, tmp_path):
        manager._output_dir = tmp_path / "deep" / "nested"
        job = _make_job(log_output=True)
        path = await manager.deliver(job, "run789", "Nested")
        assert Path(path).read_text().endswith("Nested")


class TestChannelDelivery:
    @pytest.fixture()
    def mock_channel_store(self):
        store = MagicMock()
        return store

    @pytest.fixture()
    def mock_conversation_store(self):
        store = MagicMock()
        return store

    @pytest.fixture()
    def manager(self, tmp_path, mock_channel_store, mock_conversation_store):
        return DeliveryManager(
            output_dir=tmp_path / "output",
            channel_store=mock_channel_store,
            conversation_store=mock_conversation_store,
        )

    async def test_deliver_to_single_channel(
        self, manager, mock_channel_store, mock_conversation_store,
    ):
        mock_channel = MagicMock()
        mock_channel.conversation_id = "conv-1"
        mock_channel_store.get_or_create.return_value = mock_channel

        mock_conversation = MagicMock()
        mock_conversation.messages = []
        mock_conversation_store.load.return_value = mock_conversation

        job = _make_job(channels=["briefing"], log_output=False)
        path = await manager.deliver(job, "run1", "News update")

        # Channel was looked up
        mock_channel_store.get_or_create.assert_called_once_with(
            "briefing",
            name="test_job",
            conversation_store=mock_conversation_store,
        )
        # Conversation was loaded and saved
        mock_conversation_store.load.assert_called_once_with("conv-1")
        mock_conversation_store.save.assert_called_once_with(mock_conversation)
        # Two messages appended: system + assistant
        assert len(mock_conversation.messages) == 2
        assert mock_conversation.messages[0]["role"] == "system"
        assert "test_job" in mock_conversation.messages[0]["content"]
        assert mock_conversation.messages[1]["role"] == "assistant"
        assert mock_conversation.messages[1]["content"] == "News update"
        # No file output since log_output=False and no path from channels
        assert path == ""

    async def test_deliver_to_multiple_channels(
        self, manager, mock_channel_store, mock_conversation_store,
    ):
        mock_channel_a = MagicMock()
        mock_channel_a.conversation_id = "conv-a"
        mock_channel_b = MagicMock()
        mock_channel_b.conversation_id = "conv-b"
        mock_channel_store.get_or_create.side_effect = [mock_channel_a, mock_channel_b]

        conv_a = MagicMock()
        conv_a.messages = []
        conv_b = MagicMock()
        conv_b.messages = []
        mock_conversation_store.load.side_effect = [conv_a, conv_b]

        job = _make_job(channels=["briefing", "dev-updates"], log_output=True)
        path = await manager.deliver(job, "run2", "Multi-channel output")

        assert mock_channel_store.get_or_create.call_count == 2
        assert mock_conversation_store.save.call_count == 2
        # File log also created because log_output=True
        assert path.endswith(".md")

    async def test_no_channels_skips_channel_delivery(
        self, manager, mock_channel_store, mock_conversation_store, tmp_path,
    ):
        job = _make_job(channels=[], log_output=True)
        path = await manager.deliver(job, "run3", "File only")

        mock_channel_store.get_or_create.assert_not_called()
        assert path.endswith(".md")

    async def test_channel_delivery_failure_does_not_raise(
        self, manager, mock_channel_store, mock_conversation_store,
    ):
        mock_channel_store.get_or_create.side_effect = RuntimeError("db error")

        job = _make_job(channels=["broken"], log_output=True)
        # Should not raise — channel failures are logged, not propagated
        path = await manager.deliver(job, "run4", "Still works")
        assert path.endswith(".md")

    async def test_missing_conversation_skips_channel(
        self, manager, mock_channel_store, mock_conversation_store,
    ):
        mock_channel = MagicMock()
        mock_channel.conversation_id = "conv-missing"
        mock_channel_store.get_or_create.return_value = mock_channel
        mock_conversation_store.load.return_value = None  # not found

        job = _make_job(channels=["stale"], log_output=True)
        path = await manager.deliver(job, "run5", "Output text")

        mock_conversation_store.save.assert_not_called()
        assert path.endswith(".md")


class TestBusIntegration:
    async def test_bus_message_posted(self, tmp_path):
        mock_bus = MagicMock()
        mock_channel_store = MagicMock()
        mock_conversation_store = MagicMock()

        manager = DeliveryManager(
            output_dir=tmp_path / "output",
            bus=mock_bus,
            channel_store=mock_channel_store,
            conversation_store=mock_conversation_store,
        )

        job = _make_job(channels=["briefing"], log_output=True)
        await manager.deliver(job, "run-bus", "Bus test")

        assert mock_bus.post.call_count == 1
        msg = mock_bus.post.call_args[0][0]
        assert msg.type == "job_delivery"
        assert msg.payload["job_name"] == "test_job"
        assert msg.payload["run_id"] == "run-bus"
        assert msg.payload["channels"] == ["briefing"]
