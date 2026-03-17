"""Tests for echo guard: SelfEchoDetector, VAD threshold switching,
and PlaybackProcessor signals."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import numpy as np

from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.event import EventDirection, PipelineEvent
from tank_backend.pipeline.processor import FlowReturn
from tank_backend.pipeline.wrappers.echo_guard import (
    EchoGuardConfig,
    SelfEchoDetector,
    _tokenize,
)

# ── _tokenize ────────────────────────────────────────────────────────────────


class TestTokenize:
    def test_basic(self):
        assert _tokenize("Hello World") == {"hello", "world"}

    def test_strips_punctuation(self):
        assert _tokenize("Hello, world! How's it going?") == {
            "hello", "world", "hows", "it", "going",
        }

    def test_empty(self):
        assert _tokenize("") == set()
        assert _tokenize("   ") == set()

    def test_chinese(self):
        # Chinese characters are kept as-is (no word boundaries)
        tokens = _tokenize("你好 世界")
        assert "你好" in tokens
        assert "世界" in tokens

    def test_mixed(self):
        tokens = _tokenize("Hello 你好 world")
        assert tokens == {"hello", "你好", "world"}


# ── SelfEchoDetector ─────────────────────────────────────────────────────────


class TestSelfEchoDetector:
    def _make_detector(self, **kwargs):
        config = EchoGuardConfig(**kwargs)
        return SelfEchoDetector(config)

    def test_no_tts_recorded_no_echo(self):
        det = self._make_detector()
        assert det.is_echo("hello world") is False

    def test_exact_echo_detected(self):
        det = self._make_detector(similarity_threshold=0.6)
        det.record_tts("The weather today is sunny and warm")
        assert det.is_echo("The weather today is sunny and warm") is True

    def test_partial_echo_detected(self):
        det = self._make_detector(similarity_threshold=0.6)
        det.record_tts("The weather today is sunny and warm")
        # 4/5 tokens overlap = 0.8 > 0.6
        assert det.is_echo("weather today is sunny") is True

    def test_different_text_not_echo(self):
        det = self._make_detector(similarity_threshold=0.6)
        det.record_tts("The weather today is sunny and warm")
        assert det.is_echo("Can you play some music please") is False

    def test_low_overlap_not_echo(self):
        det = self._make_detector(similarity_threshold=0.6)
        det.record_tts("The weather today is sunny and warm")
        # 1/4 tokens overlap = 0.25 < 0.6
        assert det.is_echo("today I want pizza") is False

    def test_disabled_config(self):
        det = self._make_detector(enabled=False)
        det.record_tts("hello world")
        assert det.is_echo("hello world") is False

    def test_window_eviction(self):
        det = self._make_detector(window_seconds=0.1)
        det.record_tts("hello world foo bar baz")
        time.sleep(0.15)
        # Entry should be evicted
        assert det.is_echo("hello world foo bar baz") is False

    def test_multiple_tts_entries(self):
        det = self._make_detector(similarity_threshold=0.5)
        det.record_tts("first sentence here")
        det.record_tts("second sentence there")
        # "first here" overlaps with first entry: 2/2 = 1.0
        assert det.is_echo("first here") is True
        # "second there" overlaps with second entry: 2/2 = 1.0
        assert det.is_echo("second there") is True

    def test_clear(self):
        det = self._make_detector()
        det.record_tts("hello world foo bar baz")
        det.clear()
        assert det.is_echo("hello world foo bar baz") is False

    def test_empty_transcript(self):
        det = self._make_detector()
        det.record_tts("hello world")
        assert det.is_echo("") is False
        assert det.is_echo("   ") is False

    def test_empty_tts_not_recorded(self):
        det = self._make_detector()
        det.record_tts("")
        det.record_tts("   ")
        assert len(det._recent_tts) == 0


# ── EchoGuardConfig defaults ────────────────────────────────────────────────


class TestEchoGuardConfig:
    def test_defaults(self):
        cfg = EchoGuardConfig()
        assert cfg.enabled is True
        assert cfg.vad_threshold_during_playback == 0.85
        assert cfg.similarity_threshold == 0.6
        assert cfg.window_seconds == 10.0

    def test_custom_vad_threshold(self):
        cfg = EchoGuardConfig(vad_threshold_during_playback=0.9)
        assert cfg.vad_threshold_during_playback == 0.9


# ── VADProcessor playback threshold switching ────────────────────────────────


class TestVADProcessorThresholdSwitching:
    def _make_vad_processor(self, bus=None, playback_threshold=0.85):
        from tank_backend.pipeline.wrappers.vad_processor import VADProcessor

        vad = MagicMock()
        vad.process_frame = MagicMock()
        vad.set_threshold = MagicMock()
        vad.reset_threshold = MagicMock()

        if bus is None:
            bus = Bus()

        proc = VADProcessor(vad=vad, bus=bus, playback_threshold=playback_threshold)
        return proc, vad, bus

    def test_raises_threshold_on_playback_started(self):
        proc, vad, bus = self._make_vad_processor(playback_threshold=0.85)

        bus.post(BusMessage(type="playback_started", source="playback", payload=None))
        bus.poll()

        vad.set_threshold.assert_called_once_with(0.85)

    def test_restores_threshold_on_playback_ended(self):
        proc, vad, bus = self._make_vad_processor(playback_threshold=0.85)

        bus.post(BusMessage(type="playback_ended", source="playback", payload=None))
        bus.poll()

        vad.reset_threshold.assert_called_once()

    def test_no_subscription_when_threshold_is_none(self):
        """When playback_threshold is None, no bus subscriptions are made."""
        from tank_backend.pipeline.wrappers.vad_processor import VADProcessor

        bus = Bus()
        vad = MagicMock()
        VADProcessor(vad=vad, bus=bus, playback_threshold=None)

        bus.post(BusMessage(type="playback_started", source="playback", payload=None))
        bus.poll()

        vad.set_threshold.assert_not_called()

    def test_full_cycle_raise_and_restore(self):
        proc, vad, bus = self._make_vad_processor(playback_threshold=0.9)

        bus.post(BusMessage(type="playback_started", source="playback", payload=None))
        bus.poll()
        vad.set_threshold.assert_called_once_with(0.9)

        bus.post(BusMessage(type="playback_ended", source="playback", payload=None))
        bus.poll()
        vad.reset_threshold.assert_called_once()


# ── PlaybackProcessor playback_started / playback_ended ──────────────────────


class TestPlaybackProcessorSignals:
    async def test_posts_playback_started_on_first_chunk(self):
        bus = Bus()
        messages = []
        bus.subscribe("playback_started", lambda m: messages.append(m))

        from tank_backend.pipeline.wrappers.playback_processor import PlaybackProcessor

        callback = MagicMock()
        proc = PlaybackProcessor(playback_callback=callback, bus=bus)

        chunk = MagicMock()
        chunk.pcm = np.ones(160, dtype=np.float32)

        async for _status, _output in proc.process(chunk):
            pass

        bus.poll()
        assert len(messages) == 1
        assert messages[0].type == "playback_started"

    async def test_no_duplicate_playback_started(self):
        """Only first chunk triggers playback_started."""
        bus = Bus()
        messages = []
        bus.subscribe("playback_started", lambda m: messages.append(m))

        from tank_backend.pipeline.wrappers.playback_processor import PlaybackProcessor

        callback = MagicMock()
        proc = PlaybackProcessor(playback_callback=callback, bus=bus)

        chunk = MagicMock()
        chunk.pcm = np.ones(160, dtype=np.float32)

        for _ in range(5):
            async for _status, _output in proc.process(chunk):
                pass

        bus.poll()
        assert len(messages) == 1

    async def test_flush_posts_playback_ended(self):
        bus = Bus()
        messages = []
        bus.subscribe("playback_ended", lambda m: messages.append(m))

        from tank_backend.pipeline.wrappers.playback_processor import PlaybackProcessor

        callback = MagicMock()
        proc = PlaybackProcessor(playback_callback=callback, bus=bus)

        # Start playback
        chunk = MagicMock()
        chunk.pcm = np.ones(160, dtype=np.float32)
        async for _status, _output in proc.process(chunk):
            pass

        # Flush
        event = PipelineEvent(
            type="flush", direction=EventDirection.DOWNSTREAM, source="test"
        )
        proc.handle_event(event)

        bus.poll()
        assert len(messages) == 1
        assert messages[0].type == "playback_ended"

    async def test_interrupt_posts_playback_ended(self):
        bus = Bus()
        messages = []
        bus.subscribe("playback_ended", lambda m: messages.append(m))

        from tank_backend.pipeline.wrappers.playback_processor import PlaybackProcessor

        callback = MagicMock()
        proc = PlaybackProcessor(playback_callback=callback, bus=bus)

        # Start playback
        chunk = MagicMock()
        chunk.pcm = np.ones(160, dtype=np.float32)
        async for _status, _output in proc.process(chunk):
            pass

        # Interrupt
        event = PipelineEvent(
            type="interrupt", direction=EventDirection.DOWNSTREAM, source="test"
        )
        proc.handle_event(event)

        bus.poll()
        assert len(messages) == 1
        assert messages[0].type == "playback_ended"

    async def test_no_playback_ended_if_not_playing(self):
        """Flush without prior playback should not post playback_ended."""
        bus = Bus()
        messages = []
        bus.subscribe("playback_ended", lambda m: messages.append(m))

        from tank_backend.pipeline.wrappers.playback_processor import PlaybackProcessor

        proc = PlaybackProcessor(bus=bus)

        event = PipelineEvent(
            type="flush", direction=EventDirection.DOWNSTREAM, source="test"
        )
        proc.handle_event(event)

        bus.poll()
        assert len(messages) == 0


# ── Brain echo guard integration (Brain is now a native Processor) ───────────


class TestBrainEchoGuard:
    def _make_brain(self, bus=None, echo_config=None):
        import threading
        from unittest.mock import MagicMock

        from tank_backend.config.settings import VoiceAssistantConfig
        from tank_backend.core.brain import Brain

        if bus is None:
            bus = Bus()

        mock_llm = MagicMock()
        mock_tool_manager = MagicMock()
        mock_tool_manager.get_openai_tools.return_value = []

        brain = Brain(
            llm=mock_llm,
            tool_manager=mock_tool_manager,
            config=VoiceAssistantConfig(),
            bus=bus,
            interrupt_event=threading.Event(),
            echo_guard_config=echo_config,
        )
        return brain

    def _make_event(self, text="hello world", confidence=None):
        from tank_backend.core.events import BrainInputEvent, InputType

        return BrainInputEvent(
            type=InputType.AUDIO,
            text=text,
            user="User",
            language="en",
            confidence=confidence,
        )

    async def test_echo_guard_discards_self_echo(self):
        config = EchoGuardConfig(similarity_threshold=0.5)
        brain = self._make_brain(echo_config=config)

        # Record TTS text
        brain._echo_detector.record_tts("the weather is sunny and warm today")

        # ASR produces similar text
        event = self._make_event("the weather is sunny and warm")

        results = []
        async for status, output in brain.process(event):
            results.append((status, output))

        # Should be discarded — not forwarded to LLM
        assert len(results) == 1
        assert results[0] == (FlowReturn.OK, None)
        brain._llm.chat_stream.assert_not_called()

    async def test_echo_guard_passes_different_text(self):
        from tank_backend.core.events import UpdateType

        config = EchoGuardConfig(similarity_threshold=0.5)
        brain = self._make_brain(echo_config=config)

        brain._echo_detector.record_tts("the weather is sunny and warm today")

        # Mock LLM to return a response
        async def async_gen(*args, **kwargs):
            yield UpdateType.TEXT, "Sure!", {}

        brain._llm.chat_stream.return_value = async_gen()

        event = self._make_event("can you play some music for me please")

        results = []
        async for status, output in brain.process(event):
            results.append((status, output))

        # Should pass through to LLM
        brain._llm.chat_stream.assert_called_once()

    async def test_echo_discarded_metric_posted(self):
        bus = Bus()
        messages = []
        bus.subscribe("echo_discarded", lambda m: messages.append(m))

        config = EchoGuardConfig(similarity_threshold=0.5)
        brain = self._make_brain(bus=bus, echo_config=config)

        brain._echo_detector.record_tts("the weather is sunny and warm today")
        event = self._make_event("the weather is sunny and warm")

        async for _ in brain.process(event):
            pass

        bus.poll()
        assert len(messages) == 1
        assert messages[0].payload["reason"] == "self_echo"
