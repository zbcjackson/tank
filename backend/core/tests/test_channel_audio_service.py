"""Tests for ChannelAudioService."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tank_backend.channels.audio_service import ChannelAudioService
from tank_backend.channels.subscription import ChannelSubscriptionManager


@dataclass(frozen=True)
class FakeAudioChunk:
    data: bytes
    sample_rate: int = 24000
    channels: int = 1


class FakeTTSEngine:
    """Fake TTS engine that yields predetermined chunks."""

    def __init__(self, chunks: list[bytes] | None = None) -> None:
        self._chunks = chunks or [b"chunk1", b"chunk2", b"chunk3"]
        self.generate_calls: list[dict[str, Any]] = []

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Any = None,
    ):
        self.generate_calls.append({"text": text, "language": language})
        for chunk_data in self._chunks:
            if is_interrupted and is_interrupted():
                return
            yield FakeAudioChunk(data=chunk_data)


class FakeConnectionManager:
    """Fake ConnectionManager that records sends."""

    def __init__(self) -> None:
        self._text_senders: dict[str, AsyncMock] = {}
        self._binary_senders: dict[str, AsyncMock] = {}

    def add_session(self, session_id: str) -> tuple[AsyncMock, AsyncMock]:
        text_fn = AsyncMock()
        binary_fn = AsyncMock()
        self._text_senders[session_id] = text_fn
        self._binary_senders[session_id] = binary_fn
        return text_fn, binary_fn

    def get_text_sender(self, session_id: str):
        return self._text_senders.get(session_id)

    def get_binary_sender(self, session_id: str):
        return self._binary_senders.get(session_id)


@pytest.fixture
def sub_mgr() -> ChannelSubscriptionManager:
    return ChannelSubscriptionManager()


@pytest.fixture
def conn_mgr() -> FakeConnectionManager:
    return FakeConnectionManager()


@pytest.fixture
def tts_engine() -> FakeTTSEngine:
    return FakeTTSEngine()


@pytest.fixture
def service(
    tts_engine: FakeTTSEngine,
    sub_mgr: ChannelSubscriptionManager,
    conn_mgr: FakeConnectionManager,
) -> ChannelAudioService:
    return ChannelAudioService(
        tts_engine=tts_engine,  # type: ignore[arg-type]
        subscription_manager=sub_mgr,
        connection_manager=conn_mgr,  # type: ignore[arg-type]
    )


class TestSkipWhenNoSubscribers:
    async def test_no_tts_when_no_subscribers(
        self, service: ChannelAudioService, tts_engine: FakeTTSEngine,
    ) -> None:
        await service.speak("empty-channel", "Hello world")
        assert tts_engine.generate_calls == []

    async def test_no_tts_after_unsubscribe(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])
        sub_mgr.unsubscribe("s1", ["ch"])
        await service.speak("ch", "Hello")
        assert tts_engine.generate_calls == []


class TestStreamToSubscribers:
    async def test_single_subscriber_receives_audio(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        text_fn, binary_fn = conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["news"])

        await service.speak("news", "Breaking news", {"source": "job_delivery"})

        assert tts_engine.generate_calls == [{"text": "Breaking news", "language": "en"}]
        # Should receive: start signal, 3 chunks, end signal
        assert text_fn.call_count == 2  # start + end
        assert binary_fn.call_count == 3  # 3 chunks

        # Verify start signal contains channel_slug
        start_call = text_fn.call_args_list[0][0][0]
        assert "channel_audio_start" in start_call
        assert "news" in start_call

        # Verify end signal
        end_call = text_fn.call_args_list[1][0][0]
        assert "channel_audio_end" in end_call

    async def test_multiple_subscribers_receive_audio(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
    ) -> None:
        text_fn1, binary_fn1 = conn_mgr.add_session("s1")
        text_fn2, binary_fn2 = conn_mgr.add_session("s2")
        sub_mgr.subscribe("s1", ["ch"])
        sub_mgr.subscribe("s2", ["ch"])

        await service.speak("ch", "Hello both")

        # Both should receive start + end signals and audio chunks
        assert text_fn1.call_count == 2
        assert text_fn2.call_count == 2
        assert binary_fn1.call_count == 3
        assert binary_fn2.call_count == 3


class TestSerialization:
    async def test_same_channel_serialized(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        # Launch two speaks concurrently
        await asyncio.gather(
            service.speak("ch", "First"),
            service.speak("ch", "Second"),
        )

        # Both should complete (serialized)
        assert len(tts_engine.generate_calls) == 2

    async def test_different_channels_parallel(
        self,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
    ) -> None:
        conn_mgr.add_session("s1")
        conn_mgr.add_session("s2")
        sub_mgr.subscribe("s1", ["ch-a"])
        sub_mgr.subscribe("s2", ["ch-b"])

        tts = FakeTTSEngine()
        svc = ChannelAudioService(
            tts_engine=tts,  # type: ignore[arg-type]
            subscription_manager=sub_mgr,
            connection_manager=conn_mgr,  # type: ignore[arg-type]
        )

        await asyncio.gather(
            svc.speak("ch-a", "A"),
            svc.speak("ch-b", "B"),
        )

        assert len(tts.generate_calls) == 2


class TestDisconnectHandling:
    async def test_missing_sender_skipped(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
    ) -> None:
        # Subscribe but don't add sender (simulates disconnect)
        sub_mgr.subscribe("ghost", ["ch"])

        # Should not raise
        await service.speak("ch", "Hello ghost")

    async def test_failing_sender_does_not_crash(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
    ) -> None:
        text_fn, binary_fn = conn_mgr.add_session("s1")
        binary_fn.side_effect = ConnectionError("gone")
        sub_mgr.subscribe("s1", ["ch"])

        # Should not raise despite send failures
        await service.speak("ch", "Hello")


class TestStop:
    async def test_stop_prevents_new_speaks(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        await service.stop()
        await service.speak("ch", "Should be skipped")

        assert tts_engine.generate_calls == []


class TestTextNormalization:
    """Channel audio should strip markdown/emoji/special chars before TTS,
    matching the interactive pipeline's TTSProcessor behavior."""

    async def test_markdown_stripped(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        await service.speak("ch", "**Bold** and `code` and [link](http://x)")

        # The spoken text should not contain markdown artifacts
        spoken = tts_engine.generate_calls[0]["text"]
        assert "**" not in spoken
        assert "`" not in spoken
        assert "](http" not in spoken
        # Meaningful content survives
        assert "Bold" in spoken
        assert "link" in spoken

    async def test_headers_stripped(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        await service.speak("ch", "# Daily Report\n\nAll systems normal.")

        spoken = tts_engine.generate_calls[0]["text"]
        # The "#" marker itself shouldn't be spoken
        assert not spoken.lstrip().startswith("#")
        assert "Daily Report" in spoken
        assert "All systems normal" in spoken

    async def test_empty_after_normalization_skips_tts(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        # Content that normalizes to empty (just a code block)
        await service.speak("ch", "```\nprint('hi')\n```")

        # No TTS invoked when nothing is speakable
        assert tts_engine.generate_calls == []


class TestLanguageDetection:
    async def test_chinese_text_detected(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        await service.speak("ch", "你好,今天天气怎么样?")

        assert tts_engine.generate_calls == [
            {"text": "你好,今天天气怎么样?", "language": "zh"}
        ]

    async def test_english_text_defaults_to_en(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        await service.speak("ch", "Hello world")

        assert tts_engine.generate_calls == [{"text": "Hello world", "language": "en"}]

    async def test_mixed_content_picks_zh(
        self,
        service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        await service.speak("ch", "Server status: 正常运行")

        assert tts_engine.generate_calls == [
            {"text": "Server status: 正常运行", "language": "zh"}
        ]


class TestInterrupt:
    async def test_interrupt_stops_mid_stream(
        self,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
    ) -> None:
        text_fn, binary_fn = conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        # TTS engine that checks interrupt between each chunk (3 total)
        tts = FakeTTSEngine(chunks=[b"c1", b"c2", b"c3"])
        service = ChannelAudioService(
            tts_engine=tts,  # type: ignore[arg-type]
            subscription_manager=sub_mgr,
            connection_manager=conn_mgr,  # type: ignore[arg-type]
        )

        # Interrupt BEFORE speak starts — stream exits immediately
        service.interrupt("ch")
        await service.speak("ch", "Should be interrupted")

        # Start + end signals still sent
        assert text_fn.call_count == 2
        # No audio chunks delivered because interrupt was observed
        assert binary_fn.call_count == 0

    async def test_interrupt_scoped_per_channel(
        self,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
    ) -> None:
        text_fn_a, binary_fn_a = conn_mgr.add_session("a")
        text_fn_b, binary_fn_b = conn_mgr.add_session("b")
        sub_mgr.subscribe("a", ["ch-a"])
        sub_mgr.subscribe("b", ["ch-b"])

        tts = FakeTTSEngine(chunks=[b"c1", b"c2"])
        service = ChannelAudioService(
            tts_engine=tts,  # type: ignore[arg-type]
            subscription_manager=sub_mgr,
            connection_manager=conn_mgr,  # type: ignore[arg-type]
        )

        # Only interrupt ch-a
        service.interrupt("ch-a")

        await service.speak("ch-a", "A")
        await service.speak("ch-b", "B")

        # ch-a interrupted: no chunks
        assert binary_fn_a.call_count == 0
        # ch-b unaffected: got both chunks
        assert binary_fn_b.call_count == 2

    async def test_interrupt_cleared_after_stream(
        self,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
    ) -> None:
        text_fn, binary_fn = conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        tts = FakeTTSEngine(chunks=[b"c1", b"c2"])
        service = ChannelAudioService(
            tts_engine=tts,  # type: ignore[arg-type]
            subscription_manager=sub_mgr,
            connection_manager=conn_mgr,  # type: ignore[arg-type]
        )

        service.interrupt("ch")
        await service.speak("ch", "First — interrupted")
        # Second call should NOT be interrupted (flag cleared)
        await service.speak("ch", "Second — full")

        # First delivery: 0 chunks. Second: 2 chunks. Total: 2
        assert binary_fn.call_count == 2
