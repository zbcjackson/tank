"""Integration tests for channel audio delivery system."""

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
    """Fake TTS engine for integration tests."""

    def __init__(self, chunks: list[bytes] | None = None) -> None:
        self._chunks = chunks or [b"audio1", b"audio2"]
        self.call_count = 0

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Any = None,
    ):
        self.call_count += 1
        for chunk_data in self._chunks:
            if is_interrupted and is_interrupted():
                return
            yield FakeAudioChunk(data=chunk_data)


class FakeConnectionManager:
    """Fake ConnectionManager for integration tests."""

    def __init__(self) -> None:
        self._text_senders: dict[str, AsyncMock] = {}
        self._binary_senders: dict[str, AsyncMock] = {}
        self._session_channels: dict[str, str | None] = {}

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

    def set_session_channel(self, session_id: str, slug: str | None) -> None:
        self._session_channels[session_id] = slug

    def get_session_channel(self, session_id: str) -> str | None:
        return self._session_channels.get(session_id)


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
def audio_service(
    tts_engine: FakeTTSEngine,
    sub_mgr: ChannelSubscriptionManager,
    conn_mgr: FakeConnectionManager,
) -> ChannelAudioService:
    return ChannelAudioService(
        tts_engine=tts_engine,  # type: ignore[arg-type]
        subscription_manager=sub_mgr,
        connection_manager=conn_mgr,  # type: ignore[arg-type]
    )


class TestDeliveryToSubscriber:
    """Simulates cron job delivery → TTS → audio sent to subscriber."""

    async def test_full_delivery_flow(
        self,
        audio_service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        text_fn, binary_fn = conn_mgr.add_session("client-1")
        sub_mgr.subscribe("client-1", ["daily-report"])

        await audio_service.speak(
            "daily-report",
            "Today's summary: all systems operational.",
            {"source": "job_delivery", "job_name": "Daily Report"},
        )

        # TTS was called
        assert tts_engine.call_count == 1

        # Client received start signal, audio chunks, end signal
        assert text_fn.call_count == 2
        start_json = text_fn.call_args_list[0][0][0]
        end_json = text_fn.call_args_list[1][0][0]
        assert "channel_audio_start" in start_json
        assert "daily-report" in start_json
        assert "job_delivery" in start_json
        assert "channel_audio_end" in end_json

        # Audio chunks delivered
        assert binary_fn.call_count == 2
        assert binary_fn.call_args_list[0][0][0] == b"audio1"
        assert binary_fn.call_args_list[1][0][0] == b"audio2"


class TestNoSubscriberSkip:
    """TTS is skipped when no subscribers exist."""

    async def test_no_tts_without_subscribers(
        self,
        audio_service: ChannelAudioService,
        tts_engine: FakeTTSEngine,
    ) -> None:
        await audio_service.speak("empty-channel", "Nobody listening")
        assert tts_engine.call_count == 0

    async def test_no_tts_after_disconnect(
        self,
        audio_service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])
        sub_mgr.remove_session("s1")

        await audio_service.speak("ch", "After disconnect")
        assert tts_engine.call_count == 0


class TestMultiClientSameChannel:
    """Two clients on the same channel both receive audio."""

    async def test_both_clients_hear_delivery(
        self,
        audio_service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
    ) -> None:
        text_fn1, binary_fn1 = conn_mgr.add_session("client-a")
        text_fn2, binary_fn2 = conn_mgr.add_session("client-b")
        sub_mgr.subscribe("client-a", ["shared-channel"])
        sub_mgr.subscribe("client-b", ["shared-channel"])

        await audio_service.speak("shared-channel", "Shared message")

        # Both received start + end signals
        assert text_fn1.call_count == 2
        assert text_fn2.call_count == 2

        # Both received audio chunks
        assert binary_fn1.call_count == 2
        assert binary_fn2.call_count == 2


class TestSerializationPerChannel:
    """Multiple deliveries to the same channel are serialized."""

    async def test_sequential_delivery(
        self,
        audio_service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        text_fn, binary_fn = conn_mgr.add_session("s1")
        sub_mgr.subscribe("s1", ["ch"])

        # Fire two deliveries concurrently
        await asyncio.gather(
            audio_service.speak("ch", "First delivery"),
            audio_service.speak("ch", "Second delivery"),
        )

        # Both completed (serialized by lock)
        assert tts_engine.call_count == 2

        # Client received 4 text signals (2 starts + 2 ends)
        assert text_fn.call_count == 4

        # Audio chunks: 2 per delivery = 4 total
        assert binary_fn.call_count == 4


class TestDisconnectMidStream:
    """Subscriber disconnects mid-stream — no crash."""

    async def test_graceful_disconnect(
        self,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
    ) -> None:
        text_fn, binary_fn = conn_mgr.add_session("s1")
        # Binary sender fails after first chunk (simulates disconnect)
        call_count = 0

        async def failing_binary(data: bytes) -> None:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise ConnectionError("Client disconnected")

        conn_mgr._binary_senders["s1"] = AsyncMock(side_effect=failing_binary)
        sub_mgr.subscribe("s1", ["ch"])

        tts = FakeTTSEngine(chunks=[b"c1", b"c2", b"c3"])
        service = ChannelAudioService(
            tts_engine=tts,  # type: ignore[arg-type]
            subscription_manager=sub_mgr,
            connection_manager=conn_mgr,  # type: ignore[arg-type]
        )

        # Should not raise
        await service.speak("ch", "Partial delivery")

        # TTS still ran
        assert tts.call_count == 1
        # End signal still sent (text sender didn't fail)
        assert text_fn.call_count == 2


class TestSubscriptionLifecycle:
    """Full subscription lifecycle: subscribe → receive → unsubscribe → no receive."""

    async def test_lifecycle(
        self,
        audio_service: ChannelAudioService,
        sub_mgr: ChannelSubscriptionManager,
        conn_mgr: FakeConnectionManager,
        tts_engine: FakeTTSEngine,
    ) -> None:
        text_fn, binary_fn = conn_mgr.add_session("s1")

        # Not subscribed — no audio
        await audio_service.speak("news", "Before subscribe")
        assert tts_engine.call_count == 0

        # Subscribe
        sub_mgr.subscribe("s1", ["news"])

        # Now receives audio
        await audio_service.speak("news", "After subscribe")
        assert tts_engine.call_count == 1
        assert binary_fn.call_count == 2

        # Unsubscribe
        sub_mgr.unsubscribe("s1", ["news"])

        # No more audio
        await audio_service.speak("news", "After unsubscribe")
        assert tts_engine.call_count == 1  # unchanged
