"""Integration test: Brain Processor → TTS → Playback.

Reproduces the real runtime flow where Brain runs as a native Processor,
yields AudioOutputRequest directly, and the pipeline forwards it to TTS → Playback.
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import MagicMock

import numpy as np

from tank_backend.config.settings import VoiceAssistantConfig
from tank_backend.core.events import (
    BrainInputEvent,
    DisplayMessage,
    InputType,
    SignalMessage,
    UpdateType,
)
from tank_backend.pipeline.builder import PipelineBuilder
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import Brain
from tank_backend.pipeline.processors.playback import PlaybackProcessor
from tank_backend.pipeline.processors.tts import TTSProcessor


def _fake_tts_stream(text, language=None, voice=None, is_interrupted=None):
    """Async generator that yields 3 fake audio chunks."""

    async def _gen():
        for _ in range(3):
            yield MagicMock(pcm=np.zeros(480, dtype=np.float32))

    return _gen()


def _make_brain(bus, interrupt_event, llm_response="Response to input", tts_enabled=True):
    """Create a Brain processor with a mock LLM that returns the given response."""
    mock_llm = MagicMock()

    async def async_gen(*args, **kwargs):
        yield UpdateType.TEXT, llm_response, {}

    mock_llm.chat_stream.return_value = async_gen()

    mock_tool_manager = MagicMock()
    mock_tool_manager.get_openai_tools.return_value = []

    return Brain(
        llm=mock_llm,
        tool_manager=mock_tool_manager,
        config=VoiceAssistantConfig(),
        bus=bus,
        interrupt_event=interrupt_event,
        tts_enabled=tts_enabled,
    )


class TestBrainTTSPlaybackIntegration:
    """End-to-end: Brain Processor → TTS → Playback."""

    async def test_brain_output_reaches_playback(self):
        """AudioOutputRequest from Brain must flow through TTS to Playback."""
        bus = Bus()
        interrupt_event = threading.Event()
        playback_received: list = []

        brain = _make_brain(bus, interrupt_event)

        tts_mock = MagicMock()
        tts_mock.generate_stream = _fake_tts_stream

        pipeline = (
            PipelineBuilder(bus)
            .add(brain)
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(PlaybackProcessor(
                playback_callback=lambda chunk: playback_received.append(chunk),
                bus=bus,
            ))
            .build()
        )

        await pipeline.start()
        try:
            # Push input directly to brain's queue
            pipeline.push(
                BrainInputEvent(
                    type=InputType.TEXT,
                    text="hello",
                    user="test",
                    language="en",
                    confidence=None,
                )
            )

            # Wait for the full chain: Brain → TTS → Playback
            deadline = time.monotonic() + 5.0
            while len(playback_received) < 3 and time.monotonic() < deadline:
                await asyncio.sleep(0.1)

            assert len(playback_received) == 3, (
                f"Expected 3 playback chunks, got {len(playback_received)}"
            )
        finally:
            await pipeline.stop()

    async def test_ui_messages_reach_bus(self):
        """UI messages (processing_started, text chunks) must reach the bus."""
        bus = Bus()
        interrupt_event = threading.Event()
        ui_messages: list = []

        bus.subscribe("ui_message", lambda m: ui_messages.append(m))

        brain = _make_brain(bus, interrupt_event, llm_response="Hi there")

        tts_mock = MagicMock()
        tts_mock.generate_stream = _fake_tts_stream

        pipeline = (
            PipelineBuilder(bus)
            .add(brain)
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(PlaybackProcessor(
                playback_callback=lambda _: None,
                bus=bus,
            ))
            .build()
        )

        await pipeline.start()
        try:
            pipeline.push(
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
            await pipeline.stop()

    async def test_playback_works_after_interrupt(self):
        """After a speech interrupt, the next Brain response must still
        reach Playback (flushed flag must be cleared)."""
        bus = Bus()
        interrupt_event = threading.Event()
        playback_received: list = []

        tts_mock = MagicMock()
        tts_mock.generate_stream = _fake_tts_stream

        playback_proc = PlaybackProcessor(
            playback_callback=lambda chunk: playback_received.append(chunk),
            bus=bus,
        )

        # First brain for first request
        brain1 = _make_brain(bus, interrupt_event, llm_response="First response")

        pipeline = (
            PipelineBuilder(bus)
            .add(brain1)
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(playback_proc)
            .build()
        )

        await pipeline.start()
        try:
            # First request
            pipeline.push(
                BrainInputEvent(
                    type=InputType.TEXT, text="first", user="test",
                    language="en", confidence=None,
                )
            )
            deadline = time.monotonic() + 5.0
            while len(playback_received) < 3 and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            assert len(playback_received) == 3, (
                f"First request: got {len(playback_received)} chunks"
            )

            # Simulate speech interrupt
            from tank_backend.pipeline.event import PipelineEvent

            pipeline.send_event(PipelineEvent(type="interrupt", source="test"))
            pipeline.flush_all()
            interrupt_event.set()
            await asyncio.sleep(0.2)
            interrupt_event.clear()

            # Second request — need fresh LLM mock since async gen is consumed
            brain1._llm.chat_stream.return_value = (
                _async_text_gen("Second response")
            )

            playback_received.clear()
            pipeline.push(
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
            await pipeline.stop()


async def _async_text_gen(text):
    yield UpdateType.TEXT, text, {}
