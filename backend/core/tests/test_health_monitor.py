"""Tests for HealthMonitor observer."""

import time
from unittest.mock import AsyncMock, MagicMock

from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.health import PipelineHealth, ProcessorHealth, QueueHealth
from tank_backend.pipeline.observers.health_monitor import (
    HealthMonitor,
    HealthMonitorConfig,
)


def _make_queue_health(
    name: str = "q_0",
    is_stuck: bool = False,
    consumer_alive: bool = True,
    **kwargs,
) -> QueueHealth:
    return QueueHealth(
        name=name,
        size=kwargs.get("size", 0),
        maxsize=kwargs.get("maxsize", 10),
        last_consumed_at=kwargs.get("last_consumed_at", time.monotonic()),
        is_stuck=is_stuck,
        consumer_alive=consumer_alive,
    )


def _make_proc_health(
    name: str = "vad",
    is_running: bool = True,
    consecutive_failures: int = 0,
) -> ProcessorHealth:
    return ProcessorHealth(
        name=name,
        is_running=is_running,
        consecutive_failures=consecutive_failures,
        last_error=None,
    )


def _make_pipeline_health(
    queues: list[QueueHealth] | None = None,
    processors: list[ProcessorHealth] | None = None,
    running: bool = True,
) -> PipelineHealth:
    qs = queues or []
    ps = processors or []
    is_healthy = running and all(q.consumer_alive for q in qs) and not any(q.is_stuck for q in qs)
    return PipelineHealth(running=running, processors=ps, queues=qs, is_healthy=is_healthy)


class TestHealthMonitorDetection:
    def test_detects_stuck_queue(self):
        """HealthMonitor should post queue_stuck when a queue is stuck."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health(
            queues=[_make_queue_health(name="q_stuck", is_stuck=True)],
        )
        config = HealthMonitorConfig(poll_interval_s=0.1)
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        messages: list[BusMessage] = []
        bus.subscribe("queue_stuck", lambda m: messages.append(m))

        monitor._check_health()
        bus.poll()

        assert len(messages) == 1
        assert messages[0].source == "q_stuck"

    def test_detects_dead_consumer(self):
        """HealthMonitor should post processor_failure when consumer is dead."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health(
            queues=[_make_queue_health(name="q_dead", consumer_alive=False)],
        )
        config = HealthMonitorConfig(poll_interval_s=0.1, auto_restart_enabled=False)
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        messages: list[BusMessage] = []
        bus.subscribe("processor_failure", lambda m: messages.append(m))

        monitor._check_health()
        bus.poll()

        assert len(messages) == 1
        assert messages[0].payload["reason"] == "consumer_dead"

    def test_detects_consecutive_failures(self):
        """HealthMonitor should post processor_failure on consecutive failures."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health(
            processors=[_make_proc_health(name="asr", consecutive_failures=5)],
        )
        config = HealthMonitorConfig(
            poll_interval_s=0.1,
            max_consecutive_failures=3,
            auto_restart_enabled=False,
        )
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        messages: list[BusMessage] = []
        bus.subscribe("processor_failure", lambda m: messages.append(m))

        monitor._check_health()
        bus.poll()

        assert len(messages) == 1
        assert messages[0].payload["reason"] == "consecutive_failures"
        assert messages[0].payload["count"] == 5

    def test_no_alert_when_healthy(self):
        """HealthMonitor should not post alerts when everything is healthy."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health(
            queues=[_make_queue_health()],
            processors=[_make_proc_health()],
        )
        config = HealthMonitorConfig(poll_interval_s=0.1)
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        messages: list[BusMessage] = []
        bus.subscribe_all(lambda m: messages.append(m))

        monitor._check_health()
        bus.poll()

        assert len(messages) == 0


class TestHealthMonitorAutoRestart:
    def test_auto_restart_calls_pipeline(self):
        """HealthMonitor should call pipeline.restart_processor on failure."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.restart_processor = AsyncMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health(
            queues=[_make_queue_health(name="q_dead", consumer_alive=False)],
        )
        config = HealthMonitorConfig(poll_interval_s=0.1, auto_restart_enabled=True)
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        monitor._check_health()

        pipeline.restart_processor.assert_called_once_with("q_dead")

    def test_backoff_prevents_rapid_restart(self):
        """HealthMonitor should respect backoff between restarts."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.restart_processor = AsyncMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health(
            queues=[_make_queue_health(name="q_fail", consumer_alive=False)],
        )
        config = HealthMonitorConfig(
            poll_interval_s=0.1,
            auto_restart_enabled=True,
            restart_backoff_base_s=10.0,  # long backoff
        )
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        # First check triggers restart
        monitor._check_health()
        assert pipeline.restart_processor.call_count == 1

        # Second check should be blocked by backoff
        monitor._check_health()
        assert pipeline.restart_processor.call_count == 1  # no additional call

    def test_clear_backoff(self):
        """clear_backoff should allow immediate restart."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.restart_processor = AsyncMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health(
            queues=[_make_queue_health(name="q_fail", consumer_alive=False)],
        )
        config = HealthMonitorConfig(
            poll_interval_s=0.1,
            auto_restart_enabled=True,
            restart_backoff_base_s=100.0,
        )
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        monitor._check_health()
        assert pipeline.restart_processor.call_count == 1

        monitor.clear_backoff("q_fail")
        monitor._check_health()
        assert pipeline.restart_processor.call_count == 2

    def test_auto_restart_disabled(self):
        """HealthMonitor should not restart when auto_restart_enabled=False."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.restart_processor = AsyncMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health(
            queues=[_make_queue_health(name="q_dead", consumer_alive=False)],
        )
        config = HealthMonitorConfig(
            poll_interval_s=0.1, auto_restart_enabled=False
        )
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        monitor._check_health()

        pipeline.restart_processor.assert_not_called()


class TestHealthMonitorLifecycle:
    def test_start_stop(self):
        """HealthMonitor should start and stop cleanly."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health()
        config = HealthMonitorConfig(poll_interval_s=0.1)
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        monitor.start()
        time.sleep(0.2)
        monitor.stop()

        assert monitor._thread is None

    def test_double_start(self):
        """Starting twice should not create two threads."""
        bus = Bus()
        pipeline = MagicMock()
        pipeline.health_snapshot.return_value = _make_pipeline_health()
        config = HealthMonitorConfig(poll_interval_s=0.1)
        monitor = HealthMonitor(pipeline=pipeline, bus=bus, config=config)

        monitor.start()
        first_thread = monitor._thread
        monitor.start()
        assert monitor._thread is first_thread
        monitor.stop()
