"""Tests for BrainProcessor queue draining (Phase 2 upgrade).

BrainProcessor now pushes events to Brain's input queue (Brain runs in its own
QueueWorker thread). Audio outputs are drained by a background thread and pushed
to the next pipeline queue. UI messages are also drained by the background thread.
"""

from __future__ import annotations

import queue
import threading
import time
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
    """Tests for BrainProcessor draining runtime queues via background thread."""

    def _make_processor(self, runtime=None, bus=None):
        from tank_backend.pipeline.wrappers.brain_processor import BrainProcessor

        brain = MagicMock()
        brain.handle = MagicMock()
        rt = runtime or _make_runtime()
        proc = BrainProcessor(brain=brain, bus=bus, runtime=rt)
        return proc, brain, rt

    async def test_pushes_event_to_brain_input_queue(self):
        """process() should push the event to brain_input_queue."""
        rt = _make_runtime()
        proc, brain, _ = self._make_processor(runtime=rt)

        event = _make_brain_event()
        await _collect(proc, event)

        # Event should be in brain_input_queue
        assert not rt.brain_input_queue.empty()
        queued_event = rt.brain_input_queue.get_nowait()
        assert queued_event is event

    async def test_process_yields_ok_none(self):
        """process() should yield (OK, None) — outputs come from background thread."""
        rt = _make_runtime()
        proc, _, _ = self._make_processor(runtime=rt)

        outputs = await _collect(proc, _make_brain_event())

        assert len(outputs) == 1
        assert outputs[0] == (FlowReturn.OK, None)

    async def test_drain_thread_forwards_audio_to_next_queue(self):
        """Background drain thread should push audio outputs to _next_queue."""
        rt = _make_runtime()
        proc, _, _ = self._make_processor(runtime=rt)

        # Simulate next pipeline queue
        next_q = MagicMock()
        proc._next_queue = next_q

        await proc.start()
        try:
            req1 = AudioOutputRequest(content="hello", language="en")
            req2 = AudioOutputRequest(content="world", language="zh")
            rt.audio_output_queue.put(req1)
            rt.audio_output_queue.put(req2)

            # Give drain thread time to process
            time.sleep(0.3)

            assert next_q.push.call_count == 2
            next_q.push.assert_any_call(req1)
            next_q.push.assert_any_call(req2)
        finally:
            await proc.stop()

    async def test_drain_thread_posts_ui_messages_to_bus(self):
        """Background drain thread should post UI messages to bus."""
        bus = Bus()
        rt = _make_runtime()
        proc, _, _ = self._make_processor(runtime=rt, bus=bus)

        received = []
        bus.subscribe("ui_message", lambda m: received.append(m))

        await proc.start()
        try:
            # Put an audio output first (drain thread triggers on audio_output_queue)
            req = AudioOutputRequest(content="test", language="en")
            rt.audio_output_queue.put(req)

            signal = SignalMessage(signal_type="processing_started", msg_id="test_1")
            rt.ui_queue.put(signal)

            time.sleep(0.3)
            bus.poll()

            assert len(received) >= 1
            assert received[0].payload is signal
        finally:
            await proc.stop()

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

    async def test_stop_terminates_drain_thread(self):
        """stop() should terminate the background drain thread."""
        rt = _make_runtime()
        proc, _, _ = self._make_processor(runtime=rt)

        await proc.start()
        assert proc._output_thread is not None
        assert proc._output_thread.is_alive()

        await proc.stop()
        assert proc._output_thread is None
