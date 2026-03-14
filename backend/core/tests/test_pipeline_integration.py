"""Integration tests for pipeline architecture.

Tests verify data flows correctly through the full pipeline with real
components (Pipeline, ThreadedQueue, Bus, Processors) and mocked external
dependencies (LLM, TTS, ASR engines).

These tests catch two critical bugs that unit tests missed:
1. Queue chaining: processor outputs must flow to the next queue
2. Event loop nesting: BrainProcessor must not call Brain.handle() directly
"""

from __future__ import annotations

import asyncio
import queue
import threading
from unittest.mock import MagicMock

import numpy as np

from tank_backend.audio.input.types import AudioFrame
from tank_backend.audio.input.vad import VADResult, VADStatus
from tank_backend.core.events import (
    AudioOutputRequest,
    BrainInputEvent,
    InputType,
)
from tank_backend.core.runtime import RuntimeContext
from tank_backend.pipeline.builder import PipelineBuilder
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.wrappers.asr_processor import ASRProcessor
from tank_backend.pipeline.wrappers.brain_processor import BrainProcessor
from tank_backend.pipeline.wrappers.playback_processor import PlaybackProcessor
from tank_backend.pipeline.wrappers.tts_processor import TTSProcessor
from tank_backend.pipeline.wrappers.vad_processor import VADProcessor

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_audio_frame(n_samples=320, sr=16000):
    return AudioFrame(
        pcm=np.zeros(n_samples, dtype=np.float32),
        sample_rate=sr,
        timestamp_s=1.0,
    )


def _make_vad_end_speech():
    return VADResult(
        status=VADStatus.END_SPEECH,
        utterance_pcm=np.zeros(16000, dtype=np.float32),
        sample_rate=16000,
        started_at_s=1.0,
        ended_at_s=2.0,
    )


def _make_runtime():
    return RuntimeContext(
        brain_input_queue=queue.Queue(),
        audio_output_queue=queue.Queue(),
        ui_queue=queue.Queue(),
        interrupt_event=threading.Event(),
    )


# ── Level 1: Two-Processor Queue Chaining ───────────────────────────────────


class TestTwoProcessorChaining:
    """Verify data flows between adjacent processors via queue chaining."""

    async def test_vad_output_reaches_asr(self):
        """VAD END_SPEECH result should flow to ASR processor."""
        bus = Bus()

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("hello", True)

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .build()
        )

        await pipeline.start()
        try:
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(0.5)

            asr_mock.process_pcm.assert_called_once()
            pcm_arg = asr_mock.process_pcm.call_args[0][0]
            assert len(pcm_arg) == 16000
        finally:
            await pipeline.stop()

    async def test_asr_output_reaches_brain_queue(self):
        """ASR BrainInputEvent should flow to BrainProcessor → brain_input_queue."""
        bus = Bus()
        runtime = _make_runtime()

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("hello world", True)

        brain_mock = MagicMock()
        brain_mock._runtime = runtime

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(BrainProcessor(brain=brain_mock, bus=bus, runtime=runtime))
            .build()
        )

        await pipeline.start()
        try:
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(0.5)

            assert not runtime.brain_input_queue.empty()
            event = runtime.brain_input_queue.get_nowait()
            assert isinstance(event, BrainInputEvent)
            assert event.text == "hello world"
        finally:
            await pipeline.stop()

    async def test_tts_output_reaches_playback(self):
        """TTS audio chunks should flow to PlaybackProcessor."""
        bus = Bus()
        playback_received = []

        async def fake_tts_stream(text, language=None, voice=None, is_interrupted=None):
            for _ in range(3):
                yield MagicMock(pcm=np.zeros(480))

        tts_mock = MagicMock()
        tts_mock.generate_stream = fake_tts_stream

        pipeline = (
            PipelineBuilder(bus)
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(PlaybackProcessor(
                playback_callback=lambda chunk: playback_received.append(chunk),
                bus=bus,
            ))
            .build()
        )

        await pipeline.start()
        try:
            req = AudioOutputRequest(content="hello", language="en")
            pipeline.push(req)
            await asyncio.sleep(0.5)

            assert len(playback_received) == 3
        finally:
            await pipeline.stop()


# ── Level 2: Multi-Processor Flows ──────────────────────────────────────────


class TestMultiProcessorFlow:
    """Verify data flows through 3+ processors."""

    async def test_vad_asr_brain_flow(self):
        """Audio → VAD → ASR → Brain: full speech-to-text pipeline."""
        bus = Bus()
        runtime = _make_runtime()

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("what is the weather", True)

        brain_mock = MagicMock()
        brain_mock._runtime = runtime

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(BrainProcessor(brain=brain_mock, bus=bus, runtime=runtime))
            .build()
        )

        await pipeline.start()
        try:
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(0.5)

            # VAD was called
            vad_mock.process_frame.assert_called_once()
            # ASR was called with VAD output
            asr_mock.process_pcm.assert_called_once()
            # Brain received the event
            assert not runtime.brain_input_queue.empty()
            event = runtime.brain_input_queue.get_nowait()
            assert event.text == "what is the weather"
            assert event.type == InputType.AUDIO
        finally:
            await pipeline.stop()

    async def test_brain_tts_playback_flow(self):
        """Brain output → TTS → Playback: full text-to-speech pipeline."""
        bus = Bus()
        runtime = _make_runtime()
        playback_received = []

        brain_mock = MagicMock()
        brain_mock._runtime = runtime

        async def fake_tts_stream(text, language=None, voice=None, is_interrupted=None):
            for _ in range(2):
                yield MagicMock(pcm=np.zeros(480))

        tts_mock = MagicMock()
        tts_mock.generate_stream = fake_tts_stream

        pipeline = (
            PipelineBuilder(bus)
            .add(BrainProcessor(brain=brain_mock, bus=bus, runtime=runtime))
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(PlaybackProcessor(
                playback_callback=lambda chunk: playback_received.append(chunk),
                bus=bus,
            ))
            .build()
        )

        await pipeline.start()
        try:
            # Simulate Brain producing output
            runtime.audio_output_queue.put(
                AudioOutputRequest(content="It is sunny", language="en")
            )
            await asyncio.sleep(1.0)

            assert len(playback_received) == 2
        finally:
            await pipeline.stop()


# ── Level 3: Full Pipeline End-to-End ────────────────────────────────────────


class TestFullPipelineEndToEnd:
    """Verify the complete VAD → ASR → Brain → TTS → Playback flow."""

    async def test_complete_conversation_cycle(self):
        """Audio input should flow through all 5 processors to playback."""
        bus = Bus()
        runtime = _make_runtime()
        playback_received = []

        # VAD: detect speech end
        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        # ASR: transcribe
        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("hello tank", True)

        # Brain: just a mock (we simulate its output via runtime queue)
        brain_mock = MagicMock()
        brain_mock._runtime = runtime

        # TTS: generate audio chunks
        async def fake_tts_stream(text, language=None, voice=None, is_interrupted=None):
            for _ in range(3):
                yield MagicMock(pcm=np.zeros(480))

        tts_mock = MagicMock()
        tts_mock.generate_stream = fake_tts_stream

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(BrainProcessor(brain=brain_mock, bus=bus, runtime=runtime))
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(PlaybackProcessor(
                playback_callback=lambda chunk: playback_received.append(chunk),
                bus=bus,
            ))
            .build()
        )

        await pipeline.start()
        try:
            # Push audio → triggers VAD → ASR → Brain
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(0.5)

            # Verify speech-to-text path
            vad_mock.process_frame.assert_called_once()
            asr_mock.process_pcm.assert_called_once()
            assert not runtime.brain_input_queue.empty()
            event = runtime.brain_input_queue.get_nowait()
            assert event.text == "hello tank"

            # Simulate Brain producing response (normally done by Brain thread)
            runtime.audio_output_queue.put(
                AudioOutputRequest(content="Hi there!", language="en")
            )
            await asyncio.sleep(1.0)

            # Verify text-to-speech path
            assert len(playback_received) == 3
        finally:
            await pipeline.stop()

    async def test_bus_events_posted_during_flow(self):
        """Pipeline processors should post bus events as data flows through."""
        bus = Bus()
        runtime = _make_runtime()
        events_received = {}

        for event_type in ("speech_start", "speech_end", "asr_result", "llm_latency"):
            events_received[event_type] = []
            bus.subscribe(event_type, lambda m, t=event_type: events_received[t].append(m))

        # VAD: first IN_SPEECH then END_SPEECH
        call_count = 0

        def vad_process_frame(pcm, timestamp_s):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return VADResult(status=VADStatus.IN_SPEECH)
            return _make_vad_end_speech()

        vad_mock = MagicMock()
        vad_mock.process_frame.side_effect = vad_process_frame

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("test", True)

        brain_mock = MagicMock()
        brain_mock._runtime = runtime

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(BrainProcessor(brain=brain_mock, bus=bus, runtime=runtime))
            .build()
        )

        await pipeline.start()
        try:
            # First frame: IN_SPEECH → speech_start event
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(0.3)
            bus.poll()

            assert len(events_received["speech_start"]) == 1

            # Second frame: END_SPEECH → speech_end + asr_result + llm_latency
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(0.5)
            bus.poll()

            assert len(events_received["speech_end"]) == 1
            assert len(events_received["asr_result"]) == 1
            assert len(events_received["llm_latency"]) == 1
        finally:
            await pipeline.stop()

    async def test_multiple_conversation_turns(self):
        """Pipeline should handle multiple sequential speech inputs."""
        bus = Bus()
        runtime = _make_runtime()

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        transcriptions = iter(["first message", "second message", "third message"])
        asr_mock = MagicMock()
        asr_mock.process_pcm.side_effect = lambda pcm: (next(transcriptions), True)

        brain_mock = MagicMock()
        brain_mock._runtime = runtime

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(BrainProcessor(brain=brain_mock, bus=bus, runtime=runtime))
            .build()
        )

        await pipeline.start()
        try:
            for _i in range(3):
                pipeline.push(_make_audio_frame())
                await asyncio.sleep(0.3)

            # All 3 events should reach Brain's queue
            received = []
            while not runtime.brain_input_queue.empty():
                received.append(runtime.brain_input_queue.get_nowait())

            assert len(received) == 3
            assert received[0].text == "first message"
            assert received[1].text == "second message"
            assert received[2].text == "third message"
        finally:
            await pipeline.stop()

    async def test_interrupt_propagation(self):
        """Interrupt event should propagate through all processors and flush queues."""
        bus = Bus()
        runtime = _make_runtime()
        playback_received = []

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()
        vad_mock.flush = MagicMock()

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("hello", True)

        brain_mock = MagicMock()
        brain_mock._runtime = runtime

        tts_chunks_yielded = 0

        async def slow_tts_stream(text, language=None, voice=None, is_interrupted=None):
            nonlocal tts_chunks_yielded
            for _ in range(20):
                if is_interrupted and is_interrupted():
                    return
                tts_chunks_yielded += 1
                yield MagicMock(pcm=np.zeros(480))
                await asyncio.sleep(0.05)

        tts_mock = MagicMock()
        tts_mock.generate_stream = slow_tts_stream

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(BrainProcessor(brain=brain_mock, bus=bus, runtime=runtime))
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(PlaybackProcessor(
                playback_callback=lambda chunk: playback_received.append(chunk),
                bus=bus,
            ))
            .build()
        )

        await pipeline.start()
        try:
            # Start TTS generating audio
            runtime.audio_output_queue.put(
                AudioOutputRequest(content="long response", language="en")
            )
            await asyncio.sleep(0.3)

            # Send interrupt — should stop TTS and flush playback
            from tank_backend.pipeline.event import PipelineEvent

            pipeline.send_event(PipelineEvent(type="interrupt", source="test"))
            pipeline.flush_all()
            await asyncio.sleep(0.3)

            # Interrupt event should have set runtime.interrupt_event
            assert runtime.interrupt_event.is_set()

            # TTS should have been interrupted before yielding all 20 chunks
            assert tts_chunks_yielded < 20
        finally:
            await pipeline.stop()
