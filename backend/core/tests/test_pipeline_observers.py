"""Tests for pipeline observers (LatencyObserver, TurnTrackingObserver)."""

import time

from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.observers.latency import LatencyObserver
from tank_backend.pipeline.observers.turn_tracking import TurnTrackingObserver


class TestLatencyObserver:
    def test_records_latency(self):
        """Should record latency between stage_start and stage_end."""
        bus = Bus()
        observer = LatencyObserver(bus)

        t1 = time.time()
        bus.post(BusMessage(type="stage_start", source="asr", timestamp=t1))
        bus.post(BusMessage(type="stage_end", source="asr", timestamp=t1 + 0.5))
        bus.poll()

        assert len(observer.latencies) == 1
        source, elapsed = observer.latencies[0]
        assert source == "asr"
        assert abs(elapsed - 0.5) < 0.01

    def test_multiple_stages(self):
        """Should track latency for multiple stages independently."""
        bus = Bus()
        observer = LatencyObserver(bus)

        t = time.time()
        bus.post(BusMessage(type="stage_start", source="asr", timestamp=t))
        bus.post(BusMessage(type="stage_start", source="tts", timestamp=t + 0.1))
        bus.post(BusMessage(type="stage_end", source="asr", timestamp=t + 0.3))
        bus.post(BusMessage(type="stage_end", source="tts", timestamp=t + 0.6))
        bus.poll()

        assert len(observer.latencies) == 2
        sources = {s for s, _ in observer.latencies}
        assert sources == {"asr", "tts"}

    def test_end_without_start_ignored(self):
        """stage_end without matching stage_start should be ignored."""
        bus = Bus()
        observer = LatencyObserver(bus)

        bus.post(BusMessage(type="stage_end", source="orphan", timestamp=time.time()))
        bus.poll()

        assert len(observer.latencies) == 0

    def test_reset(self):
        """reset() should clear all recorded latencies."""
        bus = Bus()
        observer = LatencyObserver(bus)

        t = time.time()
        bus.post(BusMessage(type="stage_start", source="asr", timestamp=t))
        bus.post(BusMessage(type="stage_end", source="asr", timestamp=t + 0.1))
        bus.poll()

        assert len(observer.latencies) == 1
        observer.reset()
        assert len(observer.latencies) == 0


class TestTurnTrackingObserver:
    def test_counts_user_turns(self):
        """Should count user_input messages."""
        bus = Bus()
        observer = TurnTrackingObserver(bus)

        bus.post(BusMessage(type="user_input", source="mic"))
        bus.post(BusMessage(type="user_input", source="keyboard"))
        bus.poll()

        assert observer.user_turns == 2
        assert observer.assistant_turns == 0
        assert observer.total_turns == 2

    def test_counts_assistant_turns(self):
        """Should count assistant_output messages."""
        bus = Bus()
        observer = TurnTrackingObserver(bus)

        bus.post(BusMessage(type="assistant_output", source="brain"))
        bus.poll()

        assert observer.user_turns == 0
        assert observer.assistant_turns == 1
        assert observer.total_turns == 1

    def test_mixed_turns(self):
        """Should count both user and assistant turns."""
        bus = Bus()
        observer = TurnTrackingObserver(bus)

        bus.post(BusMessage(type="user_input", source="mic"))
        bus.post(BusMessage(type="assistant_output", source="brain"))
        bus.post(BusMessage(type="user_input", source="mic"))
        bus.post(BusMessage(type="assistant_output", source="brain"))
        bus.poll()

        assert observer.user_turns == 2
        assert observer.assistant_turns == 2
        assert observer.total_turns == 4

    def test_reset(self):
        """reset() should clear turn counts."""
        bus = Bus()
        observer = TurnTrackingObserver(bus)

        bus.post(BusMessage(type="user_input", source="mic"))
        bus.post(BusMessage(type="assistant_output", source="brain"))
        bus.poll()

        observer.reset()
        assert observer.user_turns == 0
        assert observer.assistant_turns == 0
        assert observer.total_turns == 0

    def test_ignores_unrelated_messages(self):
        """Should not count messages of other types."""
        bus = Bus()
        observer = TurnTrackingObserver(bus)

        bus.post(BusMessage(type="stage_start", source="asr"))
        bus.post(BusMessage(type="stage_end", source="asr"))
        bus.poll()

        assert observer.total_turns == 0
