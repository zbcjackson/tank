"""Unit tests for NotificationHub — Phase 3."""

from __future__ import annotations

import asyncio
import time

import pytest

from tank_backend.agents.notification_hub import (
    Notification,
    NotificationHub,
    NotificationHubConfig,
)
from tank_backend.pipeline.bus import Bus, BusMessage


@pytest.fixture
def bus():
    return Bus()


@pytest.fixture
def hub(bus):
    config = NotificationHubConfig(proactive_delivery=False)
    return NotificationHub(bus, config=config)


def _worker_payload(
    event: str = "completed",
    task_id: str = "t_1",
    conversation_id: str = "conv_a",
    **kwargs,
) -> dict:
    base = {
        "event": event,
        "task_id": task_id,
        "agent_def": "coder",
        "description": "fix bug",
        "originating_conversation_id": conversation_id,
        "originating_channel": None,
        "parent_msg_id": None,
        "status": event,
        "output": kwargs.get("output", "done"),
        "error": kwargs.get("error"),
    }
    base.update(kwargs)
    return base


def _job_payload(job_name: str = "daily_report", run_id: str = "r_1") -> dict:
    return {
        "job_id": "j_1",
        "job_name": job_name,
        "run_id": run_id,
        "output_path": "/tmp/output.md",
        "channels": ["general"],
    }


class TestWorkerEventNormalization:
    def test_completed_event_queued(self, bus, hub):
        payload = _worker_payload(event="completed", output="result text")
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        notifications = hub.drain("conv_a")
        assert len(notifications) == 1
        n = notifications[0]
        assert n.source == "worker"
        assert n.event_type == "completed"
        assert "fix bug" in n.summary
        assert "result text" in n.summary
        assert n.conversation_id == "conv_a"
        assert n.metadata["task_id"] == "t_1"

    def test_failed_event_queued(self, bus, hub):
        payload = _worker_payload(event="failed", error="LLM timeout")
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        notifications = hub.drain("conv_a")
        assert len(notifications) == 1
        assert "failed" in notifications[0].summary
        assert "LLM timeout" in notifications[0].summary

    def test_cancelled_event_queued(self, bus, hub):
        payload = _worker_payload(event="cancelled", error="Worker cancelled")
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        notifications = hub.drain("conv_a")
        assert len(notifications) == 1
        assert "cancelled" in notifications[0].summary

    def test_timeout_event_queued(self, bus, hub):
        payload = _worker_payload(event="timeout", error="timed out after 60s")
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        notifications = hub.drain("conv_a")
        assert len(notifications) == 1
        assert "timeout" in notifications[0].summary

    def test_non_terminal_event_ignored(self, bus, hub):
        payload = _worker_payload(event="started")
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        assert not hub.has_pending("conv_a")

    def test_missing_conversation_id_ignored(self, bus, hub):
        payload = _worker_payload(conversation_id="")
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        assert hub.drain("") == []
        assert hub.drain("conv_a") == []


class TestJobDeliveryNormalization:
    def test_job_delivery_queued_when_conversation_fn_set(self, bus, hub):
        hub.set_conversation_id_fn(lambda: "conv_x")

        payload = _job_payload(job_name="morning_brief")
        bus.post(BusMessage(type="job_delivery", source="test", payload=payload))
        bus.poll()

        notifications = hub.drain("conv_x")
        assert len(notifications) == 1
        n = notifications[0]
        assert n.source == "job"
        assert n.event_type == "delivered"
        assert "morning_brief" in n.summary
        assert n.metadata["job_name"] == "morning_brief"

    def test_job_delivery_ignored_without_conversation_fn(self, bus, hub):
        payload = _job_payload()
        bus.post(BusMessage(type="job_delivery", source="test", payload=payload))
        bus.poll()

        # No conversation_id_fn set → notification dropped
        assert not hub.has_pending("")


class TestDrainAndHasPending:
    def test_drain_is_destructive(self, bus, hub):
        payload = _worker_payload()
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        assert hub.has_pending("conv_a")
        first = hub.drain("conv_a")
        assert len(first) == 1
        assert not hub.has_pending("conv_a")
        assert hub.drain("conv_a") == []

    def test_multiple_events_accumulate(self, bus, hub):
        for i in range(3):
            payload = _worker_payload(task_id=f"t_{i}")
            bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        notifications = hub.drain("conv_a")
        assert len(notifications) == 3

    def test_conversation_id_isolation(self, bus, hub):
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(conversation_id="conv_a"),
        ))
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(conversation_id="conv_b", task_id="t_2"),
        ))
        bus.poll()

        assert len(hub.drain("conv_a")) == 1
        assert len(hub.drain("conv_b")) == 1


class TestProactiveDeliveryConfig:
    def test_proactive_disabled_does_not_schedule_timer(self, bus):
        config = NotificationHubConfig(proactive_delivery=False)
        hub = NotificationHub(bus, config=config)

        payload = _worker_payload()
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        # No timer should be scheduled (no loop set either)
        assert hub._timers == {}

    async def test_proactive_enabled_schedules_timer(self, bus):
        config = NotificationHubConfig(proactive_delivery=True, debounce_seconds=0.1)
        hub = NotificationHub(bus, config=config)
        loop = asyncio.get_running_loop()
        hub.set_loop(loop)

        payload = _worker_payload()
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        # Give the run_coroutine_threadsafe a moment to schedule
        await asyncio.sleep(0.05)
        assert "conv_a" in hub._timers


class TestToSystemMessage:
    def test_notification_to_system_message_returns_summary(self):
        n = Notification(
            source="worker",
            event_type="completed",
            summary="[Worker 'research' completed: found 3 papers]",
            detail="found 3 papers",
            priority="normal",
            conversation_id="conv_a",
            timestamp=time.time(),
            metadata={},
        )
        assert n.to_system_message() == "[Worker 'research' completed: found 3 papers]"
