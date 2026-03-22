"""Tests for MetricsCollector observer."""

import time

from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.observers.metrics_collector import MetricsCollector


def _post_and_poll(bus: Bus, msg: BusMessage) -> None:
    """Post a message and immediately poll to dispatch it."""
    bus.post(msg)
    bus.poll()


class TestMetricsCollector:
    def setup_method(self) -> None:
        self.bus = Bus()
        self.collector = MetricsCollector(self.bus)

    def test_empty_snapshot(self) -> None:
        snap = self.collector.snapshot()
        assert snap["turns"] == 0
        assert snap["echo_discards"] == 0
        assert snap["interrupts"] == 0
        assert snap["latencies"]["asr"]["last"] is None
        assert snap["latencies"]["llm"]["last"] is None
        assert snap["latencies"]["tts"]["last"] is None
        assert snap["latencies"]["end_to_end"]["last"] is None
        assert snap["langfuse_trace_ids"] == []

    def test_asr_latency_collected(self) -> None:
        _post_and_poll(self.bus, BusMessage(
            type="asr_result",
            source="asr",
            payload={"text": "hello", "is_final": True, "latency_s": 0.45},
        ))

        snap = self.collector.snapshot()
        assert snap["turns"] == 1
        assert snap["latencies"]["asr"]["last"] == 0.45
        assert snap["latencies"]["asr"]["avg"] == 0.45
        assert snap["latencies"]["asr"]["history"] == [0.45]

    def test_llm_latency_collected(self) -> None:
        _post_and_poll(self.bus, BusMessage(
            type="llm_latency",
            source="brain",
            payload={"latency_s": 1.2, "user": "User", "text_length": 5},
        ))

        snap = self.collector.snapshot()
        assert snap["latencies"]["llm"]["last"] == 1.2

    def test_tts_latency_collected(self) -> None:
        _post_and_poll(self.bus, BusMessage(
            type="tts_finished",
            source="tts",
            payload={"latency_s": 0.6, "chunk_count": 10, "interrupted": False},
        ))

        snap = self.collector.snapshot()
        assert snap["latencies"]["tts"]["last"] == 0.6

    def test_end_to_end_latency_computed(self) -> None:
        """E2E = playback_started.timestamp - asr_result.timestamp."""
        base = 1000.0

        _post_and_poll(self.bus, BusMessage(
            type="asr_result",
            source="asr",
            payload={"text": "hi", "is_final": True, "latency_s": 0.3},
            timestamp=base,
        ))
        _post_and_poll(self.bus, BusMessage(
            type="playback_started",
            source="playback",
            payload=None,
            timestamp=base + 2.5,
        ))

        snap = self.collector.snapshot()
        assert snap["latencies"]["end_to_end"]["last"] == 2.5
        assert snap["latencies"]["end_to_end"]["history"] == [2.5]

    def test_end_to_end_no_asr_result(self) -> None:
        """playback_started without prior asr_result should not record e2e."""
        _post_and_poll(self.bus, BusMessage(
            type="playback_started",
            source="playback",
            payload=None,
        ))

        snap = self.collector.snapshot()
        assert snap["latencies"]["end_to_end"]["last"] is None

    def test_echo_discard_counted(self) -> None:
        _post_and_poll(self.bus, BusMessage(
            type="echo_discarded",
            source="brain",
            payload={"reason": "self_echo", "text": "echo"},
        ))

        snap = self.collector.snapshot()
        assert snap["echo_discards"] == 1

    def test_interrupt_counted(self) -> None:
        _post_and_poll(self.bus, BusMessage(
            type="speech_start",
            source="asr",
            payload={"timestamp_s": time.time()},
        ))

        snap = self.collector.snapshot()
        assert snap["interrupts"] == 1

    def test_trace_id_collected(self) -> None:
        _post_and_poll(self.bus, BusMessage(
            type="trace_id",
            source="brain",
            payload={"trace_id": "trace_abc123"},
        ))

        snap = self.collector.snapshot()
        assert snap["langfuse_trace_ids"] == ["trace_abc123"]

    def test_multiple_turns_aggregated(self) -> None:
        base = 1000.0

        for i in range(3):
            _post_and_poll(self.bus, BusMessage(
                type="asr_result",
                source="asr",
                payload={"text": f"msg{i}", "is_final": True, "latency_s": 0.3 + i * 0.1},
                timestamp=base + i * 10,
            ))
            _post_and_poll(self.bus, BusMessage(
                type="llm_latency",
                source="brain",
                payload={"latency_s": 1.0 + i * 0.2},
            ))
            _post_and_poll(self.bus, BusMessage(
                type="tts_finished",
                source="tts",
                payload={"latency_s": 0.5 + i * 0.1},
            ))
            _post_and_poll(self.bus, BusMessage(
                type="playback_started",
                source="playback",
                payload=None,
                timestamp=base + i * 10 + 2.0,
            ))

        snap = self.collector.snapshot()
        assert snap["turns"] == 3
        assert len(snap["latencies"]["asr"]["history"]) == 3
        assert len(snap["latencies"]["llm"]["history"]) == 3
        assert len(snap["latencies"]["tts"]["history"]) == 3
        assert len(snap["latencies"]["end_to_end"]["history"]) == 3

        # Verify avg computation
        asr_avg = snap["latencies"]["asr"]["avg"]
        assert asr_avg is not None
        assert abs(asr_avg - 0.4) < 0.01  # (0.3 + 0.4 + 0.5) / 3

    def test_reset_clears_all(self) -> None:
        _post_and_poll(self.bus, BusMessage(
            type="asr_result",
            source="asr",
            payload={"text": "hi", "is_final": True, "latency_s": 0.5},
        ))
        _post_and_poll(self.bus, BusMessage(
            type="echo_discarded",
            source="brain",
            payload={},
        ))
        _post_and_poll(self.bus, BusMessage(
            type="trace_id",
            source="brain",
            payload={"trace_id": "t1"},
        ))

        self.collector.reset()
        snap = self.collector.snapshot()

        assert snap["turns"] == 0
        assert snap["echo_discards"] == 0
        assert snap["interrupts"] == 0
        assert snap["latencies"]["asr"]["history"] == []
        assert snap["langfuse_trace_ids"] == []

    def test_snapshot_is_json_serializable(self) -> None:
        """Snapshot must be JSON-serializable (no custom objects)."""
        import json

        _post_and_poll(self.bus, BusMessage(
            type="asr_result",
            source="asr",
            payload={"text": "hi", "is_final": True, "latency_s": 0.5},
        ))

        snap = self.collector.snapshot()
        # Should not raise
        json.dumps(snap)
