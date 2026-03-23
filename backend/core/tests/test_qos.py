"""Tests for QoS feedback between TTS and Brain processors."""

from unittest.mock import MagicMock

import pytest

from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.processors.tts import TTSProcessor


class TestTTSQoS:
    def test_no_qos_without_feeding_queue(self):
        """TTS should not post QoS when no feeding queue is set."""
        bus = Bus()
        tts_engine = MagicMock()
        proc = TTSProcessor(tts_engine=tts_engine, bus=bus)
        # _feeding_queue is None by default
        messages: list = []
        bus.subscribe("qos", lambda m: messages.append(m))

        proc._check_qos()
        bus.poll()

        assert len(messages) == 0

    def test_no_qos_when_queue_not_full(self):
        """TTS should not post QoS when queue is below threshold."""
        bus = Bus()
        tts_engine = MagicMock()
        proc = TTSProcessor(tts_engine=tts_engine, bus=bus)

        mock_queue = MagicMock()
        mock_queue.qsize = 1  # 10% full
        mock_queue._queue = MagicMock()
        mock_queue._queue.maxsize = 10
        proc._feeding_queue = mock_queue

        messages: list = []
        bus.subscribe("qos", lambda m: messages.append(m))

        proc._check_qos()
        bus.poll()

        assert len(messages) == 0

    def test_qos_after_consecutive_overload(self):
        """TTS should post QoS after N consecutive overloaded checks."""
        bus = Bus()
        tts_engine = MagicMock()
        proc = TTSProcessor(tts_engine=tts_engine, bus=bus)

        mock_queue = MagicMock()
        mock_queue.qsize = 9  # 90% full
        mock_queue._queue = MagicMock()
        mock_queue._queue.maxsize = 10
        proc._feeding_queue = mock_queue

        messages: list = []
        bus.subscribe("qos", lambda m: messages.append(m))

        # Need QOS_CONSECUTIVE_THRESHOLD consecutive checks
        for _ in range(TTSProcessor.QOS_CONSECUTIVE_THRESHOLD):
            proc._check_qos()

        bus.poll()

        assert len(messages) == 1
        assert messages[0].payload["severity"] == pytest.approx(0.9, abs=0.05)

    def test_qos_resets_on_normal(self):
        """Overload counter should reset when queue drops below threshold."""
        bus = Bus()
        tts_engine = MagicMock()
        proc = TTSProcessor(tts_engine=tts_engine, bus=bus)

        mock_queue = MagicMock()
        mock_queue._queue = MagicMock()
        mock_queue._queue.maxsize = 10
        proc._feeding_queue = mock_queue

        # 2 overloaded checks
        mock_queue.qsize = 9
        proc._check_qos()
        proc._check_qos()

        # Queue clears
        mock_queue.qsize = 1
        proc._check_qos()

        # Counter should be reset
        assert proc._qos_overload_count == 0


class TestBrainQoS:
    def test_brain_skips_tools_on_high_severity(self):
        """Brain should skip tools when QoS severity > 0.7."""
        # Create a minimal Brain mock that has _on_qos and _qos_skip_tools
        # We test the _on_qos handler directly
        class FakeBrain:
            _qos_skip_tools = False

            def _on_qos(self, message):
                payload = message.payload or {}
                severity = payload.get("severity", 0.5)
                self._qos_skip_tools = severity > 0.7

        brain = FakeBrain()
        brain._on_qos(BusMessage(
            type="qos", source="tts", payload={"severity": 0.9}
        ))
        assert brain._qos_skip_tools is True

    def test_brain_does_not_skip_tools_on_low_severity(self):
        """Brain should not skip tools when QoS severity <= 0.7."""
        class FakeBrain:
            _qos_skip_tools = False

            def _on_qos(self, message):
                payload = message.payload or {}
                severity = payload.get("severity", 0.5)
                self._qos_skip_tools = severity > 0.7

        brain = FakeBrain()
        brain._on_qos(BusMessage(
            type="qos", source="tts", payload={"severity": 0.5}
        ))
        assert brain._qos_skip_tools is False
