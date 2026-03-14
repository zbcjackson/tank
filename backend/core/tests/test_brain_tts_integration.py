"""Integration test: Brain thread → drain loop → TTS → Playback.

Reproduces the real runtime flow where Brain runs as a QueueWorker thread,
produces AudioOutputRequest via runtime.audio_output_queue, and the
BrainProcessor drain loop forwards it to TTS → Playback.

This test catches the bug where TTS/Playback never receive data even though
Brain finishes successfully.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from tank_backend.core.events import (
    AudioOutputRequest,
    BrainInputEvent,
    DisplayMessage,
    InputType,
    SignalMessage,
)
from tank_backend.core.runtime import RuntimeContext
from tank_backend.core.shutdown import GracefulShutdown
from tank_backend.pipeline.builder import PipelineBuilder
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.wrappers.brain_processor import BrainProcessor
from tank_backend.pipeline.wrappers.playback_processor import PlaybackProcessor
from tank_backend.pipeline.wrappers.tts_processor import TTSProcessor


def _make_runtime():
    return RuntimeContext(
        brain_input_queue=queue.Queue(),
        audio_output_queue=queue.Queue(),
        ui_queue=queue.Queue(),
        interrupt_event=threading.Event(),
    )


def _fake_tts_stream(text, language=None, voice=None, is_interrupted=None):
    """Async generator that yields 3 fake audio chunks."""

    async def _gen():
        for _ in range(3):
            yield MagicMock(pcm=np.zeros(480, dtype=np.float32))

    return _gen()


class FakeBrain:
    """Simulates Brain behavior: reads from brain_input_queue, streams LLM
    response via ui_queue, then puts AudioOutputRequest to audio_output_queue."""

    def __init__(self, runtime: RuntimeContext, shutdown: GracefulShutdown):
        self._runtime = runtime
        self._shutdown = shutdown
        self._thread: threading.Thread | None = None
        self._tts_enabled = True

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="FakeBrain")
        self._thread.start()

    def _run(self):
        while not self._shutdown.is_set():
            try:
                event: BrainInputEvent = self._runtime.brain_input_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if event.type == InputType.SYSTEM and event.text == "__reset__":
                continue

            msg_id = "assistant_test"

            # 1. Signal: processing_started
            self._runtime.ui_queue.put(
                SignalMessage(signal_type="processing_started", msg_id=msg_id)
            )

            # 2. Stream text chunks
            response = f"Response to: {event.text}"
            for i in range(0, len(response), 10):
                chunk = response[i : i + 10]
                self._runtime.ui_queue.put(
                    DisplayMessage(
                        speaker="Brain",
                        text=chunk,
                        is_user=False,
                        msg_id=msg_id,
                        is_final=False,
                    )
                )

            # 3. Final empty message
            self._runtime.ui_queue.put(
                DisplayMessage(
                    speaker="Brain", text="", is_user=False, msg_id=msg_id, is_final=True
                )
            )

            # 4. TTS request
            if self._tts_enabled:
                self._runtime.audio_output_queue.put(
                    AudioOutputRequest(content=response, language="en")
                )

            # 5. Signal: processing_ended
            self._runtime.ui_queue.put(
                SignalMessage(signal_type="processing_ended", msg_id=msg_id)
            )

    def join(self, timeout=2.0):
        if self._thread:
            self._thread.join(timeout=timeout)


class TestBrainTTSPlaybackIntegration:
    """End-to-end: FakeBrain thread → BrainProcessor drain → TTS → Playback."""

    async def test_brain_output_reaches_playback(self):
        """AudioOutputRequest from Brain thread must flow through TTS to Playback."""
        bus = Bus()
        runtime = _make_runtime()
        shutdown = GracefulShutdown()
        playback_received: list = []

        brain = FakeBrain(runtime, shutdown)
        brain_proc = BrainProcessor(brain=MagicMock(_runtime=runtime), bus=bus, runtime=runtime)

        tts_mock = MagicMock()
        tts_mock.generate_stream = _fake_tts_stream

        pipeline = (
            PipelineBuilder(bus)
            .add(brain_proc)
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(PlaybackProcessor(
                playback_callback=lambda chunk: playback_received.append(chunk),
                bus=bus,
            ))
            .build()
        )

        await pipeline.start()
        brain.start()
        try:
            # Simulate user input arriving at Brain
            runtime.brain_input_queue.put(
                BrainInputEvent(
                    type=InputType.TEXT,
                    text="hello",
                    user="test",
                    language="en",
                    confidence=None,
                )
            )

            # Wait for the full chain: Brain → drain → TTS → Playback
            deadline = time.monotonic() + 5.0
            while len(playback_received) < 3 and time.monotonic() < deadline:
                await asyncio.sleep(0.1)

            assert len(playback_received) == 3, (
                f"Expected 3 playback chunks, got {len(playback_received)}. "
                f"audio_output_queue empty={runtime.audio_output_queue.empty()}, "
                f"brain_proc._next_queue={brain_proc._next_queue}"
            )
        finally:
            shutdown.stop()
            brain.join()
            await pipeline.stop()

    async def test_ui_messages_reach_bus_before_audio(self):
        """UI messages (processing_started, text chunks) must reach the bus
        even before AudioOutputRequest is produced."""
        bus = Bus()
        runtime = _make_runtime()
        shutdown = GracefulShutdown()
        ui_messages: list = []

        bus.subscribe("ui_message", lambda m: ui_messages.append(m))

        brain = FakeBrain(runtime, shutdown)
        brain_proc = BrainProcessor(brain=MagicMock(_runtime=runtime), bus=bus, runtime=runtime)

        tts_mock = MagicMock()
        tts_mock.generate_stream = _fake_tts_stream

        pipeline = (
            PipelineBuilder(bus)
            .add(brain_proc)
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(PlaybackProcessor(
                playback_callback=lambda _: None,
                bus=bus,
            ))
            .build()
        )

        await pipeline.start()
        brain.start()
        try:
            runtime.brain_input_queue.put(
                BrainInputEvent(
                    type=InputType.TEXT,
                    text="hi",
                    user="test",
                    language="en",
                    confidence=None,
                )
            )

            # Wait for Brain to finish
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                bus.poll()
                # Check if we got processing_ended (last signal)
                signals = [
                    m for m in ui_messages
                    if isinstance(m.payload, SignalMessage)
                    and m.payload.signal_type == "processing_ended"
                ]
                if signals:
                    break
                await asyncio.sleep(0.05)

            bus.poll()

            # Verify we got processing_started
            started = [
                m for m in ui_messages
                if isinstance(m.payload, SignalMessage)
                and m.payload.signal_type == "processing_started"
            ]
            assert len(started) >= 1, (
                f"Expected processing_started signal, got signals: "
                f"{[m.payload for m in ui_messages if isinstance(m.payload, SignalMessage)]}"
            )

            # Verify we got text chunks
            text_msgs = [
                m for m in ui_messages
                if isinstance(m.payload, DisplayMessage) and not m.payload.is_user
            ]
            assert len(text_msgs) >= 1, "Expected at least one text chunk from Brain"
        finally:
            shutdown.stop()
            brain.join()
            await pipeline.stop()

    async def test_playback_works_after_interrupt(self):
        """After a speech interrupt, the next Brain response must still
        reach Playback (flushed flag must be cleared)."""
        bus = Bus()
        runtime = _make_runtime()
        shutdown = GracefulShutdown()
        playback_received: list = []

        brain = FakeBrain(runtime, shutdown)
        brain_proc = BrainProcessor(brain=MagicMock(_runtime=runtime), bus=bus, runtime=runtime)

        tts_mock = MagicMock()
        tts_mock.generate_stream = _fake_tts_stream

        playback_proc = PlaybackProcessor(
            playback_callback=lambda chunk: playback_received.append(chunk),
            bus=bus,
        )

        pipeline = (
            PipelineBuilder(bus)
            .add(brain_proc)
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(playback_proc)
            .build()
        )

        await pipeline.start()
        brain.start()
        try:
            # First request
            runtime.brain_input_queue.put(
                BrainInputEvent(
                    type=InputType.TEXT, text="first", user="test",
                    language="en", confidence=None,
                )
            )
            deadline = time.monotonic() + 5.0
            while len(playback_received) < 3 and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            assert len(playback_received) == 3, f"First request: got {len(playback_received)} chunks"

            # Simulate speech interrupt
            from tank_backend.pipeline.event import PipelineEvent

            pipeline.send_event(PipelineEvent(type="interrupt", source="test"))
            pipeline.flush_all()
            runtime.interrupt_event.set()
            await asyncio.sleep(0.2)
            runtime.interrupt_event.clear()

            # Second request — must still reach playback
            playback_received.clear()
            runtime.brain_input_queue.put(
                BrainInputEvent(
                    type=InputType.TEXT, text="second", user="test",
                    language="en", confidence=None,
                )
            )
            deadline = time.monotonic() + 5.0
            while len(playback_received) < 3 and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            assert len(playback_received) == 3, (
                f"Second request after interrupt: got {len(playback_received)} chunks. "
                f"playback._flushed={playback_proc._flushed}"
            )
        finally:
            shutdown.stop()
            brain.join()
            await pipeline.stop()
