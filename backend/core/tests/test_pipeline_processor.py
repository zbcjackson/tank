"""Tests for pipeline Processor ABC and FlowReturn."""

import pytest

from tank_backend.pipeline.processor import AudioCaps, FlowReturn, Processor


class TestFlowReturn:
    def test_flow_return_values(self):
        """FlowReturn enum should have expected values."""
        assert FlowReturn.OK.value == "ok"
        assert FlowReturn.EOS.value == "eos"
        assert FlowReturn.FLUSHING.value == "flushing"
        assert FlowReturn.ERROR.value == "error"


class TestAudioCaps:
    def test_audio_caps_defaults(self):
        """AudioCaps should have sensible defaults."""
        caps = AudioCaps(sample_rate=16000)
        assert caps.sample_rate == 16000
        assert caps.channels == 1
        assert caps.dtype == "float32"

    def test_audio_caps_custom(self):
        """AudioCaps should accept custom values."""
        caps = AudioCaps(sample_rate=48000, channels=2, dtype="int16")
        assert caps.sample_rate == 48000
        assert caps.channels == 2
        assert caps.dtype == "int16"

    def test_audio_caps_frozen(self):
        """AudioCaps should be immutable."""
        caps = AudioCaps(sample_rate=16000)
        with pytest.raises(AttributeError):
            caps.sample_rate = 24000


class DummyProcessor(Processor):
    """Minimal processor for testing."""

    def __init__(self, name: str):
        super().__init__(name)
        self.started = False
        self.stopped = False

    async def process(self, item):
        yield FlowReturn.OK, f"processed_{item}"

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class TestProcessor:
    async def test_processor_name(self):
        """Processor should store its name."""
        proc = DummyProcessor("test_proc")
        assert proc.name == "test_proc"

    async def test_processor_caps_default_none(self):
        """Processor caps should default to None."""
        proc = DummyProcessor("test")
        assert proc.input_caps is None
        assert proc.output_caps is None

    async def test_processor_process(self):
        """Processor.process should yield (status, output) pairs."""
        proc = DummyProcessor("test")
        results = []
        async for status, output in proc.process("input"):
            results.append((status, output))
        assert results == [(FlowReturn.OK, "processed_input")]

    async def test_processor_start_stop(self):
        """Processor start/stop lifecycle."""
        proc = DummyProcessor("test")
        assert not proc.started
        assert not proc.stopped

        await proc.start()
        assert proc.started

        await proc.stop()
        assert proc.stopped

    async def test_processor_handle_event_default(self):
        """Processor.handle_event should return False by default (propagate)."""
        from tank_backend.pipeline.event import EventDirection, PipelineEvent

        proc = DummyProcessor("test")
        event = PipelineEvent(type="test", direction=EventDirection.DOWNSTREAM)
        consumed = proc.handle_event(event)
        assert consumed is False
