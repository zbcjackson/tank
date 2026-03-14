"""Tests for InterruptLatencyObserver."""

from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.observers.interrupt_latency import InterruptLatencyObserver


class TestInterruptLatencyObserver:
    def test_records_latency_between_speech_start_and_interrupt_ack(self):
        """Should record elapsed time between speech_start and interrupt_ack."""
        bus = Bus()
        observer = InterruptLatencyObserver(bus)

        bus.post(BusMessage(type="speech_start", source="vad", timestamp=100.0))
        bus.post(BusMessage(type="interrupt_ack", source="tts", timestamp=100.05))
        bus.poll()

        assert len(observer.latencies) == 1
        source, elapsed = observer.latencies[0]
        assert source == "tts"
        assert abs(elapsed - 0.05) < 1e-6

    def test_no_latency_without_speech_start(self):
        """interrupt_ack without prior speech_start should not record."""
        bus = Bus()
        observer = InterruptLatencyObserver(bus)

        bus.post(BusMessage(type="interrupt_ack", source="tts", timestamp=100.0))
        bus.poll()

        assert len(observer.latencies) == 0

    def test_multiple_cycles(self):
        """Should track multiple speech_start → interrupt_ack cycles."""
        bus = Bus()
        observer = InterruptLatencyObserver(bus)

        bus.post(BusMessage(type="speech_start", source="vad", timestamp=100.0))
        bus.post(BusMessage(type="interrupt_ack", source="tts", timestamp=100.03))
        bus.post(BusMessage(type="speech_start", source="vad", timestamp=200.0))
        bus.post(BusMessage(type="interrupt_ack", source="brain", timestamp=200.1))
        bus.poll()

        assert len(observer.latencies) == 2
        assert observer.latencies[0][0] == "tts"
        assert observer.latencies[1][0] == "brain"

    def test_reset_clears_state(self):
        """reset() should clear latencies and pending speech_start."""
        bus = Bus()
        observer = InterruptLatencyObserver(bus)

        bus.post(BusMessage(type="speech_start", source="vad", timestamp=100.0))
        bus.post(BusMessage(type="interrupt_ack", source="tts", timestamp=100.05))
        bus.poll()

        assert len(observer.latencies) == 1
        observer.reset()
        assert len(observer.latencies) == 0

    def test_speech_start_resets_pending(self):
        """A new speech_start should overwrite the previous pending timestamp."""
        bus = Bus()
        observer = InterruptLatencyObserver(bus)

        bus.post(BusMessage(type="speech_start", source="vad", timestamp=100.0))
        bus.post(BusMessage(type="speech_start", source="vad", timestamp=200.0))
        bus.post(BusMessage(type="interrupt_ack", source="tts", timestamp=200.02))
        bus.poll()

        assert len(observer.latencies) == 1
        _, elapsed = observer.latencies[0]
        assert abs(elapsed - 0.02) < 1e-6
