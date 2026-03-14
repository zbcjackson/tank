"""Tests for BrainProcessor queue draining (Phase 2 upgrade)."""

from __future__ import annotations

import queue
import threading
from unittest.mock import MagicMock

from tank_backend.core.events import (
    AudioOutputRequest,
    BrainInputEvent,
    DisplayMessage,
    InputType,
    SignalMessage,
)
from tank_backend.core.runtime import RuntimeContext
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processor import FlowReturn


async def _collect(processor, item):
    """Collect all (status, output) pairs from processor.process(item)."""
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


def _make_brain_event(text="hello"):
    return BrainInputEvent(
        type=InputType.AUDIO,
        text=text,
        user="User",
        language="zh",
        confidence=None,
    )


def _make_runtime():
    return RuntimeContext(
        brain_input_queue=queue.Queue(),
        audio_output_queue=queue.Queue(),
        ui_queue=queue.Queue(),
        interrupt_event=threading.Event(),
    )


class TestBrainProcessorDrain:
    """Tests for BrainProcessor draining runtime queues after brain.handle()."""

    def _make_processor(self, runtime=None, bus=None):
        from tank_backend.pipeline.wrappers.brain_processor import BrainProcessor

        brain = MagicMock()
        brain.handle = MagicMock()
        rt = runtime or _make_runtime()
        proc = BrainProcessor(brain=brain, bus=bus, runtime=rt)
        return proc, brain, rt

    async def test_drains_audio_output_queue(self):
        """After brain.handle(), audio_output_queue items should be yielded downstream."""
        rt = _make_runtime()
        proc, brain, _ = self._make_processor(runtime=rt)

        req1 = AudioOutputRequest(content="hello", language="en")
        req2 = AudioOutputRequest(content="world", language="zh")

        def fake_handle(event):
            rt.audio_output_queue.put(req1)
            rt.audio_output_queue.put(req2)

        brain.handle = fake_handle

        outputs = await _collect(proc, _make_brain_event())

        assert len(outputs) == 2
        assert outputs[0] == (FlowReturn.OK, req1)
        assert outputs[1] == (FlowReturn.OK, req2)

    async def test_drains_ui_queue_to_bus(self):
        """After brain.handle(), ui_queue items should be posted to Bus as ui_message."""
        bus = Bus()
        rt = _make_runtime()
        proc, brain, _ = self._make_processor(runtime=rt, bus=bus)

        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        signal = SignalMessage(signal_type="processing_started", msg_id="test_1")
        display = DisplayMessage(
            speaker="Brain", text="hello", is_user=False, msg_id="test_1"
        )

        def fake_handle(event):
            rt.ui_queue.put(signal)
            rt.ui_queue.put(display)

        brain.handle = fake_handle

        await _collect(proc, _make_brain_event())
        bus.poll()

        assert len(received) == 2
        assert received[0].payload is signal
        assert received[1].payload is display

    async def test_drains_both_queues(self):
        """Both audio_output_queue and ui_queue should be drained."""
        bus = Bus()
        rt = _make_runtime()
        proc, brain, _ = self._make_processor(runtime=rt, bus=bus)

        ui_received = []
        bus.subscribe("ui_message", lambda m: ui_received.append(m))

        req = AudioOutputRequest(content="test", language="en")
        signal = SignalMessage(signal_type="processing_started")

        def fake_handle(event):
            rt.audio_output_queue.put(req)
            rt.ui_queue.put(signal)

        brain.handle = fake_handle

        outputs = await _collect(proc, _make_brain_event())
        bus.poll()

        # Audio output yielded downstream
        assert len(outputs) == 1
        assert outputs[0][1] is req

        # UI message posted to bus
        assert len(ui_received) == 1
        assert ui_received[0].payload is signal

    async def test_empty_queues_yield_nothing(self):
        """If brain.handle() doesn't populate queues, no items should be yielded."""
        bus = Bus()
        rt = _make_runtime()
        proc, brain, _ = self._make_processor(runtime=rt, bus=bus)

        ui_received = []
        bus.subscribe("ui_message", lambda m: ui_received.append(m))

        # brain.handle() does nothing (queues stay empty)
        outputs = await _collect(proc, _make_brain_event())
        bus.poll()

        assert len(outputs) == 0
        assert len(ui_received) == 0

    async def test_still_posts_llm_latency(self):
        """LLM latency metric should still be posted to bus."""
        bus = Bus()
        rt = _make_runtime()
        proc, _, _ = self._make_processor(runtime=rt, bus=bus)

        latency_received = []
        bus.subscribe("llm_latency", lambda m: latency_received.append(m))

        await _collect(proc, _make_brain_event())
        bus.poll()

        assert len(latency_received) == 1
        assert "latency_s" in latency_received[0].payload

    async def test_interrupt_event_uses_runtime(self):
        """Interrupt event should set runtime.interrupt_event via the explicit runtime ref."""
        from tank_backend.pipeline.event import EventDirection, PipelineEvent

        rt = _make_runtime()
        proc, _, _ = self._make_processor(runtime=rt)

        event = PipelineEvent(type="interrupt", direction=EventDirection.UPSTREAM)
        consumed = proc.handle_event(event)

        assert consumed is False
        assert rt.interrupt_event.is_set()

    async def test_no_bus_skips_ui_drain(self):
        """Without a bus, ui_queue items should not cause errors."""
        rt = _make_runtime()
        proc, brain, _ = self._make_processor(runtime=rt, bus=None)

        def fake_handle(event):
            rt.ui_queue.put(SignalMessage(signal_type="test"))
            rt.audio_output_queue.put(AudioOutputRequest(content="hi"))

        brain.handle = fake_handle

        outputs = await _collect(proc, _make_brain_event())

        # Audio output still yielded
        assert len(outputs) == 1
        assert outputs[0][1].content == "hi"

        # UI message stays in queue (no bus to drain to)
        assert not rt.ui_queue.empty()
