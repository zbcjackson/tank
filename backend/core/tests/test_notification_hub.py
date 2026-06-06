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

    def test_started_event_tracked_not_queued(self, bus, hub):
        payload = _worker_payload(event="started")
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        assert not hub.has_pending("conv_a")
        # But it should be tracked in pending workers
        assert "t_1" in hub._pending_workers.get("conv_a", set())

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

    def test_drain_clears_pending_workers(self, bus, hub):
        # Start a worker
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(event="started", task_id="t_1"),
        ))
        bus.poll()
        assert "t_1" in hub._pending_workers.get("conv_a", set())

        # Complete it
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(event="completed", task_id="t_1"),
        ))
        bus.poll()

        # Drain should clear pending_workers too
        hub.drain("conv_a")
        assert "conv_a" not in hub._pending_workers


class TestCohortTracking:
    def test_started_events_tracked(self, bus, hub):
        for i in range(3):
            bus.post(BusMessage(
                type="worker", source="test",
                payload=_worker_payload(event="started", task_id=f"t_{i}"),
            ))
        bus.poll()

        assert hub._pending_workers["conv_a"] == {"t_0", "t_1", "t_2"}
        assert not hub.has_pending("conv_a")

    def test_terminal_event_removes_from_pending(self, bus, hub):
        # Start 3 workers
        for i in range(3):
            bus.post(BusMessage(
                type="worker", source="test",
                payload=_worker_payload(event="started", task_id=f"t_{i}"),
            ))
        bus.poll()

        # Complete one
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(event="completed", task_id="t_0"),
        ))
        bus.poll()

        assert hub._pending_workers["conv_a"] == {"t_1", "t_2"}
        assert hub.has_pending("conv_a")

    def test_all_workers_complete_marks_cohort_done(self, bus, hub):
        # Start 2 workers
        for i in range(2):
            bus.post(BusMessage(
                type="worker", source="test",
                payload=_worker_payload(event="started", task_id=f"t_{i}"),
            ))
        bus.poll()

        # Complete both
        for i in range(2):
            bus.post(BusMessage(
                type="worker", source="test",
                payload=_worker_payload(event="completed", task_id=f"t_{i}"),
            ))
        bus.poll()

        # All done — pending_workers set is empty
        assert hub._pending_workers.get("conv_a") == set()
        # Notifications are queued
        assert hub.has_pending("conv_a")
        notifications = hub.drain("conv_a")
        assert len(notifications) == 2

    def test_legacy_path_no_started_event(self, bus, hub):
        """Terminal event without prior started event still works."""
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(event="completed", task_id="t_orphan"),
        ))
        bus.poll()

        assert hub.has_pending("conv_a")
        notifications = hub.drain("conv_a")
        assert len(notifications) == 1


class TestProactiveDeliveryConfig:
    def test_proactive_disabled_does_not_schedule_timer(self, bus):
        config = NotificationHubConfig(proactive_delivery=False)
        hub = NotificationHub(bus, config=config)

        payload = _worker_payload()
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        # No timers scheduled
        assert hub._settle_timers == {}
        assert hub._max_wait_timers == {}

    @pytest.mark.asyncio
    async def test_proactive_cohort_done_schedules_settle_timer(self, bus):
        config = NotificationHubConfig(
            proactive_delivery=True, settle_seconds=0.1,
        )
        hub = NotificationHub(bus, config=config)
        loop = asyncio.get_running_loop()
        hub.set_loop(loop)

        # Start and immediately complete (no started event → legacy path)
        payload = _worker_payload()
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        # Give the run_coroutine_threadsafe a moment to schedule
        await asyncio.sleep(0.05)
        assert "conv_a" in hub._settle_timers

    @pytest.mark.asyncio
    async def test_proactive_cohort_not_done_schedules_max_wait(self, bus):
        config = NotificationHubConfig(
            proactive_delivery=True, settle_seconds=0.1, max_wait_seconds=1.0,
        )
        hub = NotificationHub(bus, config=config)
        loop = asyncio.get_running_loop()
        hub.set_loop(loop)

        # Start a worker, then complete one of two
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(event="started", task_id="t_0"),
        ))
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(event="started", task_id="t_1"),
        ))
        bus.poll()

        # Complete only t_0
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(event="completed", task_id="t_0"),
        ))
        bus.poll()

        await asyncio.sleep(0.05)
        # Should have max-wait timer, not settle timer
        assert "conv_a" in hub._max_wait_timers
        assert "conv_a" not in hub._settle_timers

    @pytest.mark.asyncio
    async def test_settle_timer_fires_and_delivers(self, bus):
        config = NotificationHubConfig(
            proactive_delivery=True, settle_seconds=0.05,
        )
        hub = NotificationHub(bus, config=config)
        loop = asyncio.get_running_loop()
        hub.set_loop(loop)
        # No pipeline set → injection won't happen, but timer logic runs

        payload = _worker_payload()
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        await asyncio.sleep(0.15)
        # Timer fired (settle_timers should be cleared)
        assert "conv_a" not in hub._settle_timers

    @pytest.mark.asyncio
    async def test_max_wait_fires_delivers_partial(self, bus):
        config = NotificationHubConfig(
            proactive_delivery=True, settle_seconds=0.5, max_wait_seconds=0.1,
        )
        hub = NotificationHub(bus, config=config)
        loop = asyncio.get_running_loop()
        hub.set_loop(loop)

        # Start 2 workers
        for i in range(2):
            bus.post(BusMessage(
                type="worker", source="test",
                payload=_worker_payload(event="started", task_id=f"t_{i}"),
            ))
        bus.poll()

        # Complete only 1
        bus.post(BusMessage(
            type="worker", source="test",
            payload=_worker_payload(event="completed", task_id="t_0"),
        ))
        bus.poll()

        await asyncio.sleep(0.05)
        assert "conv_a" in hub._max_wait_timers

        # Wait for max-wait to fire
        await asyncio.sleep(0.15)
        # Max-wait fired, pending_workers cleared
        assert "conv_a" not in hub._pending_workers
        assert "conv_a" not in hub._max_wait_timers


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
