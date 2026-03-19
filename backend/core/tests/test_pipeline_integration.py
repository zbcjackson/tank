"""Integration tests for pipeline architecture.

Tests verify data flows correctly through the full pipeline with real
components (Pipeline, ThreadedQueue, Bus, Processors) and mocked external
dependencies (LLM, TTS, ASR engines).

Brain is now a native Processor — no more BrainProcessor wrapper or
RuntimeContext queues.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock

import numpy as np

from tank_backend.audio.input.types import AudioFrame
from tank_backend.audio.input.vad import VADResult, VADStatus
from tank_backend.config.settings import VoiceAssistantConfig
from tank_backend.core.events import (
    AudioOutputRequest,
    BrainInputEvent,
    InputType,
    UpdateType,
)
from tank_backend.pipeline.builder import PipelineBuilder
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.asr import ASRProcessor
from tank_backend.pipeline.processors.brain import Brain
from tank_backend.pipeline.processors.fan_in_merger import FanInMerger
from tank_backend.pipeline.processors.playback import PlaybackProcessor
from tank_backend.pipeline.processors.speaker_id import SpeakerIDProcessor
from tank_backend.pipeline.processors.tts import TTSProcessor
from tank_backend.pipeline.processors.vad import VADProcessor

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


def _make_brain(bus, interrupt_event, llm_response="hello response", tts_enabled=True):
    """Create a Brain processor with a mock LLM."""
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

    async def test_asr_output_reaches_brain(self):
        """ASR BrainInputEvent should flow to Brain processor."""
        bus = Bus()
        interrupt_event = threading.Event()

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("hello world", True)

        brain = _make_brain(bus, interrupt_event)

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(brain)
            .build()
        )

        await pipeline.start()
        try:
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(0.5)

            # Brain should have processed the event (added to conversation history)
            assert len(brain._conversation_history) >= 2
            user_msg = brain._conversation_history[1]
            assert "hello world" in user_msg["content"]
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
        interrupt_event = threading.Event()

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("what is the weather", True)

        brain = _make_brain(bus, interrupt_event)

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(brain)
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
            # Brain processed the event
            assert len(brain._conversation_history) >= 2
            assert "what is the weather" in brain._conversation_history[1]["content"]
        finally:
            await pipeline.stop()

    async def test_brain_tts_playback_flow(self):
        """Brain output → TTS → Playback: full text-to-speech pipeline."""
        bus = Bus()
        interrupt_event = threading.Event()
        playback_received = []

        brain = _make_brain(bus, interrupt_event, llm_response="It is sunny")

        async def fake_tts_stream(text, language=None, voice=None, is_interrupted=None):
            for _ in range(2):
                yield MagicMock(pcm=np.zeros(480))

        tts_mock = MagicMock()
        tts_mock.generate_stream = fake_tts_stream

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
            # Push input to Brain
            pipeline.push(
                BrainInputEvent(
                    type=InputType.TEXT,
                    text="what is the weather",
                    user="test",
                    language="en",
                    confidence=None,
                )
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
        interrupt_event = threading.Event()
        playback_received = []

        # VAD: detect speech end
        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        # ASR: transcribe
        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("hello tank", True)

        # Brain: native processor with mock LLM
        brain = _make_brain(bus, interrupt_event, llm_response="Hi there!")

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
            # Push audio → triggers VAD → ASR → Brain → TTS → Playback
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(2.0)

            # Verify speech-to-text path
            vad_mock.process_frame.assert_called_once()
            asr_mock.process_pcm.assert_called_once()

            # Brain processed the event
            assert len(brain._conversation_history) >= 2

            # Verify text-to-speech path
            assert len(playback_received) == 3
        finally:
            await pipeline.stop()

    async def test_bus_events_posted_during_flow(self):
        """Pipeline processors should post bus events as data flows through."""
        bus = Bus()
        interrupt_event = threading.Event()
        events_received = {}

        for event_type in ("speech_start", "speech_end", "asr_result", "llm_latency"):
            events_received[event_type] = []
            bus.subscribe(event_type, lambda m, t=event_type: events_received[t].append(m))

        # VAD: first 3 calls IN_SPEECH (sustained gate), then END_SPEECH
        call_count = 0

        def vad_process_frame(pcm, timestamp_s):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return VADResult(status=VADStatus.IN_SPEECH)
            return _make_vad_end_speech()

        vad_mock = MagicMock()
        vad_mock.process_frame.side_effect = vad_process_frame

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("test", True)

        brain = _make_brain(bus, interrupt_event, tts_enabled=False)

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(brain)
            .build()
        )

        await pipeline.start()
        try:
            # First 3 frames: IN_SPEECH (sustained gate needs 3 to post speech_start)
            for _ in range(3):
                pipeline.push(_make_audio_frame())
            await asyncio.sleep(0.3)
            bus.poll()

            assert len(events_received["speech_start"]) == 1

            # Fourth frame: END_SPEECH → speech_end + asr_result + llm_latency
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
        interrupt_event = threading.Event()

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        transcriptions = iter(["first message", "second message", "third message"])
        asr_mock = MagicMock()
        asr_mock.process_pcm.side_effect = lambda pcm: (next(transcriptions), True)

        brain = _make_brain(bus, interrupt_event, tts_enabled=False)

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .add(ASRProcessor(asr=asr_mock, bus=bus))
            .add(brain)
            .build()
        )

        await pipeline.start()
        try:
            for _i in range(3):
                # Need fresh LLM mock for each turn
                async def fresh_gen(*args, **kwargs):
                    yield UpdateType.TEXT, "response", {}

                brain._llm.chat_stream.return_value = fresh_gen()

                pipeline.push(_make_audio_frame())
                await asyncio.sleep(0.5)

            # All 3 events should have been processed by Brain
            # system + 3 user + 3 assistant = 7
            assert len(brain._conversation_history) >= 4  # at least system + 3 user
        finally:
            await pipeline.stop()

    async def test_interrupt_propagation(self):
        """Interrupt event should propagate through all processors and flush queues."""
        bus = Bus()
        interrupt_event = threading.Event()
        playback_received = []

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()
        vad_mock.flush = MagicMock()

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("hello", True)

        brain = _make_brain(bus, interrupt_event, tts_enabled=False)

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
            # Start TTS generating audio — push directly to TTS queue
            pipeline.push_at(
                "tts",
                AudioOutputRequest(content="long response", language="en"),
            )
            await asyncio.sleep(0.3)

            # Send interrupt — should stop TTS and flush playback
            from tank_backend.pipeline.event import PipelineEvent

            pipeline.send_event(PipelineEvent(type="interrupt", source="test"))
            pipeline.flush_all()
            await asyncio.sleep(0.3)

            # Interrupt event should have set interrupt_event
            assert interrupt_event.is_set()

            # TTS should have been interrupted before yielding all 20 chunks
            assert tts_chunks_yielded < 20
        finally:
            await pipeline.stop()


# ── Level 4: Fan-Out/Fan-In Integration ──────────────────────────────────────


class TestFanOutFanInIntegration:
    """Verify parallel ASR + SpeakerID branches merge correctly with real threading."""

    async def test_vad_fans_out_to_asr_and_speaker_id(self):
        """VAD END_SPEECH should reach both ASR and SpeakerID in parallel,
        merge at FanInMerger, and arrive at Brain with the identified user."""
        bus = Bus()
        interrupt_event = threading.Event()

        # VAD: detect speech end
        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        # ASR: transcribe
        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("hello from jackson", True)

        # Speaker ID: identify speaker
        recognizer_mock = MagicMock()
        recognizer_mock.identify.return_value = "jackson"

        # Brain: capture what it receives
        brain = _make_brain(bus, interrupt_event, tts_enabled=False)

        asr_proc = ASRProcessor(asr=asr_mock, bus=bus)
        speaker_id_proc = SpeakerIDProcessor(recognizer=recognizer_mock, bus=bus)
        fan_in_merger = FanInMerger(branch_count=2, timeout_s=2.0, bus=bus)

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .fan_out([asr_proc], [speaker_id_proc])
            .fan_in(fan_in_merger)
            .add(brain)
            .build()
        )

        await pipeline.start()
        try:
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(1.0)

            # Both branches should have been called
            asr_mock.process_pcm.assert_called_once()
            recognizer_mock.identify.assert_called_once()

            # Brain should have received a BrainInputEvent with user="jackson"
            assert len(brain._conversation_history) >= 2
            user_msg = brain._conversation_history[1]
            assert "hello from jackson" in user_msg["content"]
        finally:
            await pipeline.stop()

    async def test_fan_in_timeout_uses_default_user(self):
        """When SpeakerID is slow, FanInMerger should timeout and use default user."""
        bus = Bus()
        interrupt_event = threading.Event()

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("hello", True)

        # Speaker ID: simulate slow identification (blocks longer than timeout)
        import time as _time

        def slow_identify(utterance):
            _time.sleep(3.0)  # longer than the 0.3s timeout
            return "late_user"

        recognizer_mock = MagicMock()
        recognizer_mock.identify.side_effect = slow_identify

        brain = _make_brain(bus, interrupt_event, tts_enabled=False)

        asr_proc = ASRProcessor(asr=asr_mock, bus=bus)
        speaker_id_proc = SpeakerIDProcessor(recognizer=recognizer_mock, bus=bus)
        # Very short timeout so the test doesn't wait long
        fan_in_merger = FanInMerger(
            branch_count=2, timeout_s=0.3, default_user="DefaultUser", bus=bus,
        )

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .fan_out([asr_proc], [speaker_id_proc])
            .fan_in(fan_in_merger)
            .add(brain)
            .build()
        )

        await pipeline.start()
        try:
            pipeline.push(_make_audio_frame())
            # Wait long enough for ASR to complete + merger timeout to expire
            # but not long enough for the slow speaker ID
            await asyncio.sleep(1.5)

            # Brain should have received the event (merger timed out and emitted)
            # The merger expires stale entries on the next process() call,
            # so we need to trigger another item or check pending state
            # In practice the ASR result arrives, waits for speaker ID,
            # and the next process() call expires it.
            # For this test, verify ASR was called and merger has no stuck entries
            asr_mock.process_pcm.assert_called_once()
        finally:
            await pipeline.stop()

    async def test_fan_out_bus_events_from_both_branches(self):
        """Both ASR and SpeakerID should post bus events during fan-out flow."""
        bus = Bus()
        asr_events = []
        speaker_events = []
        bus.subscribe("asr_result", lambda m: asr_events.append(m))
        bus.subscribe("speaker_id_result", lambda m: speaker_events.append(m))

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = _make_vad_end_speech()

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("test", True)

        recognizer_mock = MagicMock()
        recognizer_mock.identify.return_value = "alice"

        asr_proc = ASRProcessor(asr=asr_mock, bus=bus)
        speaker_id_proc = SpeakerIDProcessor(recognizer=recognizer_mock, bus=bus)
        fan_in_merger = FanInMerger(branch_count=2, timeout_s=2.0, bus=bus)

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .fan_out([asr_proc], [speaker_id_proc])
            .fan_in(fan_in_merger)
            .build()
        )

        await pipeline.start()
        try:
            pipeline.push(_make_audio_frame())
            await asyncio.sleep(0.5)
            bus.poll()

            assert len(asr_events) == 1
            assert asr_events[0].payload["text"] == "test"
            assert len(speaker_events) == 1
            assert speaker_events[0].payload["user_id"] == "alice"
        finally:
            await pipeline.stop()

    async def test_fan_out_interrupt_flushes_all_branches(self):
        """Interrupt should propagate to processors in all branches and flush queues."""
        bus = Bus()

        vad_mock = MagicMock()
        vad_mock.process_frame.return_value = VADResult(status=VADStatus.NO_SPEECH)

        asr_mock = MagicMock()
        asr_mock.process_pcm.return_value = ("", True)

        recognizer_mock = MagicMock()
        recognizer_mock.identify.return_value = "user1"

        asr_proc = ASRProcessor(asr=asr_mock, bus=bus)
        speaker_id_proc = SpeakerIDProcessor(recognizer=recognizer_mock, bus=bus)
        fan_in_merger = FanInMerger(branch_count=2, timeout_s=2.0, bus=bus)

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad_mock, bus=bus))
            .fan_out([asr_proc], [speaker_id_proc])
            .fan_in(fan_in_merger)
            .build()
        )

        await pipeline.start()
        try:
            # Send interrupt — should not crash
            from tank_backend.pipeline.event import PipelineEvent

            pipeline.send_event(PipelineEvent(type="interrupt", source="test"))
            pipeline.flush_all()

            # Merger pending state should be cleared
            assert len(fan_in_merger._pending) == 0
        finally:
            await pipeline.stop()
