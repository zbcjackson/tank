"""Tests for AlertingObserver and AlertDispatcher."""

import time
from unittest.mock import patch

from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.observers.alerting import (
    Alert,
    AlertDispatcher,
    AlertingObserver,
    AlertThresholds,
)


class TestAlertingObserverLatency:
    def test_no_alert_with_few_samples(self):
        """Should not alert with < 10 latency samples."""
        bus = Bus()
        AlertingObserver(bus=bus)  # subscribes to bus on construction
        alerts: list = []
        bus.subscribe("alert", lambda m: alerts.append(m))

        for _ in range(5):
            bus.post(BusMessage(type="llm_latency", source="llm", payload={"latency_s": 1.0}))
        bus.poll()

        assert len(alerts) == 0

    def test_latency_spike_detection(self):
        """Should alert after N consecutive latency spikes above 2x p95."""
        bus = Bus()
        thresholds = AlertThresholds(
            latency_spike_multiplier=2.0,
            latency_spike_consecutive=3,
            alert_cooldown_s=0,
        )
        AlertingObserver(bus=bus, thresholds=thresholds)  # subscribes to bus
        alerts: list = []
        bus.subscribe("alert", lambda m: alerts.append(m))

        # Build baseline: 40 samples at ~1.0s (enough to keep p95 stable)
        for _ in range(40):
            bus.post(BusMessage(type="llm_latency", source="llm", payload={"latency_s": 1.0}))
        bus.poll()

        # Now send 3 extreme spikes (>2x p95; with 40 baselines p95≈1.0, threshold=2.0)
        for _ in range(3):
            bus.post(BusMessage(type="llm_latency", source="llm", payload={"latency_s": 10.0}))
        bus.poll()
        bus.poll()  # dispatch alert posted during first poll

        alert_msgs = [a for a in alerts if a.payload.alert_type == "latency_spike"]
        assert len(alert_msgs) >= 1

    def test_latency_resets_on_normal(self):
        """Consecutive spike counter should reset on a normal-latency turn."""
        bus = Bus()
        thresholds = AlertThresholds(
            latency_spike_multiplier=2.0,
            latency_spike_consecutive=5,
            alert_cooldown_s=0,
        )
        AlertingObserver(bus=bus, thresholds=thresholds)  # subscribes to bus
        alerts: list = []
        bus.subscribe("alert", lambda m: alerts.append(m))

        # Baseline
        for _ in range(15):
            bus.post(BusMessage(type="llm_latency", source="llm", payload={"latency_s": 1.0}))
        bus.poll()

        # 2 spikes, then normal, then 2 more spikes → should not trigger (need 5 consecutive)
        for _ in range(2):
            bus.post(BusMessage(type="llm_latency", source="llm", payload={"latency_s": 5.0}))
        bus.post(BusMessage(type="llm_latency", source="llm", payload={"latency_s": 1.0}))
        for _ in range(2):
            bus.post(BusMessage(type="llm_latency", source="llm", payload={"latency_s": 5.0}))
        bus.poll()

        alert_msgs = [a for a in alerts if a.payload.alert_type == "latency_spike"]
        assert len(alert_msgs) == 0


class TestAlertingObserverErrors:
    def test_processor_failure_triggers_alert(self):
        """processor_failure bus message should produce an alert."""
        bus = Bus()
        thresholds = AlertThresholds(alert_cooldown_s=0)
        AlertingObserver(bus=bus, thresholds=thresholds)  # subscribes to bus
        alerts: list = []
        bus.subscribe("alert", lambda m: alerts.append(m))

        bus.post(BusMessage(
            type="processor_failure", source="asr",
            payload={"reason": "consecutive_failures", "count": 3},
        ))
        bus.poll()
        bus.poll()  # dispatch alert posted during first poll

        assert len(alerts) == 1
        assert alerts[0].payload.alert_type == "processor_failure"
        assert alerts[0].payload.severity == "critical"

    def test_error_rate_detection(self):
        """High error rate should trigger alert."""
        bus = Bus()
        thresholds = AlertThresholds(
            error_rate_threshold=0.10,
            error_rate_window_s=300.0,
            alert_cooldown_s=0,
        )
        AlertingObserver(bus=bus, thresholds=thresholds)  # subscribes to bus
        alerts: list = []
        bus.subscribe("alert", lambda m: alerts.append(m))

        # Register 5 turns
        for _ in range(5):
            bus.post(BusMessage(type="asr_result", source="asr", payload={}))
        bus.poll()

        # Register 2 errors (40% rate)
        bus.post(BusMessage(
            type="processor_failure", source="brain",
            payload={"reason": "error"},
        ))
        bus.post(BusMessage(
            type="processor_failure", source="brain",
            payload={"reason": "error"},
        ))
        bus.poll()
        bus.poll()  # dispatch alert posted during first poll

        error_rate_alerts = [
            a for a in alerts if a.payload.alert_type == "error_rate"
        ]
        assert len(error_rate_alerts) >= 1


class TestAlertingObserverQueueSaturation:
    def test_queue_saturation_detection(self):
        """Sustained queue_stuck messages should trigger saturation alert."""
        bus = Bus()
        thresholds = AlertThresholds(
            queue_saturation_duration_s=0.0,  # instant for testing
            alert_cooldown_s=0,
        )
        AlertingObserver(bus=bus, thresholds=thresholds)  # subscribes to bus
        alerts: list = []
        bus.subscribe("alert", lambda m: alerts.append(m))

        # First message sets the start time
        bus.post(BusMessage(type="queue_stuck", source="q_0_brain", payload={}))
        bus.poll()

        # Second message triggers (duration > 0)
        bus.post(BusMessage(type="queue_stuck", source="q_0_brain", payload={}))
        bus.poll()
        bus.poll()  # dispatch alert posted during first poll

        sat_alerts = [a for a in alerts if a.payload.alert_type == "queue_saturation"]
        assert len(sat_alerts) >= 1

    def test_queue_saturation_needs_duration(self):
        """Single queue_stuck message should not trigger alert if duration > 0."""
        bus = Bus()
        thresholds = AlertThresholds(
            queue_saturation_duration_s=60.0,  # needs 60s
            alert_cooldown_s=0,
        )
        AlertingObserver(bus=bus, thresholds=thresholds)  # subscribes to bus
        alerts: list = []
        bus.subscribe("alert", lambda m: alerts.append(m))

        bus.post(BusMessage(type="queue_stuck", source="q_0_brain", payload={}))
        bus.poll()

        sat_alerts = [a for a in alerts if a.payload.alert_type == "queue_saturation"]
        assert len(sat_alerts) == 0


class TestAlertingObserverCooldown:
    def test_cooldown_suppresses_duplicate(self):
        """Same alert type should not fire within cooldown period."""
        bus = Bus()
        thresholds = AlertThresholds(alert_cooldown_s=60.0)
        AlertingObserver(bus=bus, thresholds=thresholds)  # subscribes to bus
        alerts: list = []
        bus.subscribe("alert", lambda m: alerts.append(m))

        bus.post(BusMessage(
            type="processor_failure", source="asr",
            payload={"reason": "error"},
        ))
        bus.poll()
        bus.poll()

        bus.post(BusMessage(
            type="processor_failure", source="asr",
            payload={"reason": "error"},
        ))
        bus.poll()
        bus.poll()

        # Only one should get through
        failure_alerts = [a for a in alerts if a.payload.alert_type == "processor_failure"]
        assert len(failure_alerts) == 1


class TestAlertingObserverSnapshot:
    def test_snapshot_returns_recent_alerts(self):
        bus = Bus()
        thresholds = AlertThresholds(alert_cooldown_s=0)
        observer = AlertingObserver(bus=bus, thresholds=thresholds)

        bus.post(BusMessage(
            type="processor_failure", source="asr",
            payload={"reason": "error"},
        ))
        bus.poll()  # dispatches processor_failure → observer posts alert
        bus.poll()  # dispatches alert

        snap = observer.snapshot()
        assert len(snap) >= 1
        assert snap[0]["alert_type"] == "processor_failure"

    def test_reset_clears_state(self):
        bus = Bus()
        observer = AlertingObserver(bus=bus)
        observer._alerts.append(Alert(
            alert_type="test", severity="warning", message="test", source="test"
        ))
        observer.reset()
        assert observer.snapshot() == []


class TestAlertDispatcher:
    def test_log_only_mode(self):
        """AlertDispatcher should log alerts when no webhook is configured."""
        bus = Bus()
        AlertDispatcher(bus=bus, webhook_url=None)  # subscribes to bus

        alert = Alert(
            alert_type="test", severity="warning", message="test alert", source="test"
        )
        bus.post(BusMessage(type="alert", source="test", payload=alert))

        with patch("tank_backend.pipeline.observers.alerting.logger") as mock_logger:
            bus.poll()
            mock_logger.warning.assert_called()

    def test_webhook_dispatch(self):
        """AlertDispatcher should POST to webhook URL."""
        bus = Bus()
        AlertDispatcher(bus=bus, webhook_url="https://hooks.example.com/test")  # subscribes

        alert = Alert(
            alert_type="test", severity="warning", message="test alert", source="test"
        )
        bus.post(BusMessage(type="alert", source="test", payload=alert))

        with patch("urllib.request.urlopen") as mock_urlopen:
            bus.poll()
            # Give thread pool time to fire
            time.sleep(0.5)
            mock_urlopen.assert_called_once()

    def test_ignores_non_alert_payload(self):
        """AlertDispatcher should ignore messages with non-Alert payloads."""
        bus = Bus()
        AlertDispatcher(bus=bus, webhook_url=None)  # subscribes to bus

        bus.post(BusMessage(type="alert", source="test", payload="not_an_alert"))
        # Should not raise
        bus.poll()
