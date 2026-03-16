"""Pipeline integration test with real WAV audio fixture.

Uses real Silero VAD + real Sherpa ASR with the 你好.wav fixture,
while mocking Brain and TTS. Tests the full pipeline from audio
frames through VAD → ASR → Brain → TTS → Playback.

Requires:
- Sherpa-ONNX model at backend/models/sherpa-onnx-zipformer-en-zh/
- WAV fixture at test/fixtures/audio/你好.wav
"""

from __future__ import annotations

import asyncio
import queue
import threading
import wave
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from tank_backend.audio.input.types import AudioFrame, SegmenterConfig
from tank_backend.audio.input.vad import SileroVAD
from tank_backend.core.events import AudioOutputRequest, BrainInputEvent
from tank_backend.core.runtime import RuntimeContext
from tank_backend.pipeline.builder import PipelineBuilder
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.wrappers.asr_processor import ASRProcessor
from tank_backend.pipeline.wrappers.brain_processor import BrainProcessor
from tank_backend.pipeline.wrappers.playback_processor import PlaybackProcessor
from tank_backend.pipeline.wrappers.tts_processor import TTSProcessor
from tank_backend.pipeline.wrappers.vad_processor import VADProcessor

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = REPO_ROOT / "backend" / "models" / "sherpa-onnx-zipformer-en-zh"
WAV_PATH = REPO_ROOT / "test" / "fixtures" / "audio" / "你好.wav"

skip_no_model = pytest.mark.skipif(
    not (MODEL_DIR / "tokens.txt").exists(),
    reason="Sherpa-ONNX model not found",
)
skip_no_fixture = pytest.mark.skipif(
    not WAV_PATH.exists(),
    reason="WAV fixture not found — run scripts/generate_test_audio.py",
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_wav_frames(
    path: Path, frame_ms: int = 20,
) -> list[AudioFrame]:
    """Load a WAV file and split into AudioFrames."""
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    frame_samples = sr * frame_ms // 1000
    frames = []
    for i in range(0, len(pcm), frame_samples):
        chunk = pcm[i : i + frame_samples]
        if len(chunk) < frame_samples:
            break
        timestamp_s = (i + frame_samples) / sr
        frames.append(AudioFrame(pcm=chunk, sample_rate=sr, timestamp_s=timestamp_s))
    return frames


def _make_runtime() -> RuntimeContext:
    return RuntimeContext(
        brain_input_queue=queue.Queue(),
        audio_output_queue=queue.Queue(),
        ui_queue=queue.Queue(),
        interrupt_event=threading.Event(),
    )


# ── Tests ────────────────────────────────────────────────────────────────────


@skip_no_model
@skip_no_fixture
class TestPipelineWithRealAudio:
    """Full pipeline integration using real VAD + ASR with WAV fixture."""

    @pytest.fixture(scope="class")
    def vad(self):
        cfg = SegmenterConfig(
            speech_threshold=0.5,
            min_speech_ms=200,
            min_silence_ms=800,
            pre_roll_ms=200,
            max_utterance_ms=20000,
        )
        return SileroVAD(cfg)

    @pytest.fixture(scope="class")
    def asr_engine(self):
        from asr_sherpa.engine import SherpaASREngine

        return SherpaASREngine(model_dir=str(MODEL_DIR))

    @pytest.fixture()
    def wav_frames(self):
        return _load_wav_frames(WAV_PATH)

    async def test_full_pipeline_vad_to_playback(
        self, vad, asr_engine, wav_frames,
    ):
        """Real audio → VAD → ASR → Brain → TTS → Playback."""
        bus = Bus()
        runtime = _make_runtime()
        playback_received = []

        brain_mock = MagicMock()
        brain_mock._runtime = runtime

        async def fake_tts_stream(
            text, language=None, voice=None, is_interrupted=None,
        ):
            for _ in range(3):
                yield MagicMock(pcm=np.zeros(480))

        tts_mock = MagicMock()
        tts_mock.generate_stream = fake_tts_stream

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad, bus=bus))
            .add(ASRProcessor(asr=asr_engine, bus=bus))
            .add(BrainProcessor(brain=brain_mock, bus=bus, runtime=runtime))
            .add(TTSProcessor(tts_engine=tts_mock, bus=bus))
            .add(PlaybackProcessor(
                playback_callback=lambda c: playback_received.append(c),
                bus=bus,
            ))
            .build()
        )

        await pipeline.start()
        try:
            # Push all audio frames (simulates real-time mic input)
            for frame in wav_frames:
                pipeline.push(frame)
                await asyncio.sleep(0.005)

            # Wait for VAD silence timeout + ASR processing
            await asyncio.sleep(3.0)

            # ── Verify speech-to-text path ──
            assert not runtime.brain_input_queue.empty(), (
                "Brain should have received a BrainInputEvent"
            )
            event = runtime.brain_input_queue.get_nowait()
            assert isinstance(event, BrainInputEvent)
            assert "你好" in event.text, (
                f"Expected '你好' in transcription, got: '{event.text}'"
            )

            # ── Verify text-to-speech path ──
            # Simulate Brain producing a response
            runtime.audio_output_queue.put(
                AudioOutputRequest(content="你好！", language="zh")
            )
            await asyncio.sleep(1.0)

            assert len(playback_received) == 3, (
                f"Expected 3 TTS chunks, got {len(playback_received)}"
            )
        finally:
            await pipeline.stop()

    async def test_bus_events_with_real_audio(
        self, vad, asr_engine, wav_frames,
    ):
        """Real audio should trigger speech_start, speech_end, asr_result
        bus events."""
        bus = Bus()
        runtime = _make_runtime()
        events: dict[str, list] = {
            "speech_start": [],
            "speech_end": [],
            "asr_result": [],
        }
        for evt_type in events:
            bus.subscribe(
                evt_type,
                lambda m, t=evt_type: events[t].append(m),
            )

        brain_mock = MagicMock()
        brain_mock._runtime = runtime

        pipeline = (
            PipelineBuilder(bus)
            .add(VADProcessor(vad=vad, bus=bus))
            .add(ASRProcessor(asr=asr_engine, bus=bus))
            .add(BrainProcessor(brain=brain_mock, bus=bus, runtime=runtime))
            .build()
        )

        await pipeline.start()
        try:
            for frame in wav_frames:
                pipeline.push(frame)
                await asyncio.sleep(0.005)

            await asyncio.sleep(3.0)
            bus.poll()

            assert len(events["speech_start"]) >= 1
            assert len(events["speech_end"]) >= 1
            assert len(events["asr_result"]) >= 1

            asr_payload = events["asr_result"][0].payload
            assert "你好" in asr_payload["text"]
            assert asr_payload["latency_s"] > 0
        finally:
            await pipeline.stop()
