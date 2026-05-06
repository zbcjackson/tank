"""Channel audio service — generates TTS for channel deliveries and streams to subscribers."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..pipeline.processors.tts_normalizer import normalize_for_tts

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tank_contracts.tts import AudioChunk, TTSEngine

    from ..api.manager import ConnectionManager
    from ..channels.subscription import ChannelSubscriptionManager

logger = logging.getLogger(__name__)


def _detect_language(text: str) -> str:
    """Detect language from text content.

    Returns "zh" if any CJK character is present, otherwise "en".
    Matches the heuristic used by tts-cosyvoice and Tank's interactive path,
    which hardcodes "zh" as the primary language.
    """
    for c in text:
        if "一" <= c <= "鿿":
            return "zh"
    return "en"


class ChannelAudioService:
    """Generates TTS for channel deliveries and streams audio to subscribers.

    - Owns a shared TTSEngine instance (from plugin registry)
    - Skips TTS entirely when no subscribers exist for a channel
    - Serializes deliveries per-channel via asyncio.Lock
    - Fans out audio chunks to all subscribers simultaneously
    """

    def __init__(
        self,
        tts_engine: TTSEngine,
        subscription_manager: ChannelSubscriptionManager,
        connection_manager: ConnectionManager,
    ) -> None:
        self._tts_engine = tts_engine
        self._subscription_manager = subscription_manager
        self._connection_manager = connection_manager
        self._channel_locks: dict[str, asyncio.Lock] = {}
        self._interrupted_channels: set[str] = set()
        self._stopped = False

    def _get_channel_lock(self, channel_slug: str) -> asyncio.Lock:
        lock = self._channel_locks.get(channel_slug)
        if lock is None:
            lock = asyncio.Lock()
            self._channel_locks[channel_slug] = lock
        return lock

    def interrupt(self, channel_slug: str) -> None:
        """Interrupt an in-progress TTS stream for a channel.

        The current generate_stream loop will observe is_interrupted() == True
        and exit early. The channel_audio_end signal is still sent.
        """
        self._interrupted_channels.add(channel_slug)

    async def speak(
        self,
        channel_slug: str,
        text: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Generate TTS and stream audio to all subscribers of a channel.

        Skips TTS if no subscribers. Serializes per-channel.
        Normalizes text (strip markdown/emoji/special chars) to match the
        interactive pipeline's TTSProcessor behavior.
        """
        if self._stopped:
            return

        subscribers = self._subscription_manager.get_subscribers(channel_slug)
        if not subscribers:
            logger.debug("No subscribers for channel '%s', skipping TTS", channel_slug)
            return

        # Match interactive path: strip markdown/emoji/special chars before TTS.
        normalized_text = normalize_for_tts(text)
        if not normalized_text.strip():
            logger.info(
                "ChannelAudioService: nothing speakable after normalization for channel '%s'",
                channel_slug,
            )
            return

        lock = self._get_channel_lock(channel_slug)
        async with lock:
            # Re-check subscribers after acquiring lock (may have changed)
            subscribers = self._subscription_manager.get_subscribers(channel_slug)
            if not subscribers:
                return
            await self._stream_to_subscribers(channel_slug, normalized_text, subscribers, metadata)

    async def _stream_to_subscribers(
        self,
        channel_slug: str,
        text: str,
        subscribers: set[str],
        metadata: dict[str, str] | None,
    ) -> None:
        """Generate TTS and send audio frames to subscriber sessions."""
        from ..api.schemas import MessageType, WebsocketMessage

        meta = {"channel_slug": channel_slug, **(metadata or {})}

        # Send channel_audio_start to all subscribers
        start_msg = WebsocketMessage(
            type=MessageType.SIGNAL,
            content="channel_audio_start",
            metadata=meta,
        )
        await self._send_json_to_sessions(subscribers, start_msg.model_dump_json())

        # Stream TTS chunks
        try:
            def is_interrupted() -> bool:
                return self._stopped or channel_slug in self._interrupted_channels

            chunk_stream: AsyncIterator[AudioChunk] = self._tts_engine.generate_stream(  # type: ignore[assignment]
                text, language=_detect_language(text), is_interrupted=is_interrupted,
            )
            async for chunk in chunk_stream:
                if is_interrupted():
                    break
                await self._send_binary_to_sessions(subscribers, chunk.data)
        except Exception:
            logger.error(
                "TTS generation failed for channel '%s'", channel_slug, exc_info=True,
            )
        finally:
            # Clear any interrupt flag now that the stream is done, so the next
            # speak() for this channel starts fresh.
            self._interrupted_channels.discard(channel_slug)

        # Send channel_audio_end to all subscribers
        end_msg = WebsocketMessage(
            type=MessageType.SIGNAL,
            content="channel_audio_end",
            metadata={"channel_slug": channel_slug},
        )
        await self._send_json_to_sessions(subscribers, end_msg.model_dump_json())

    async def _send_json_to_sessions(
        self, session_ids: set[str], json_str: str,
    ) -> None:
        """Send a JSON message to specific sessions (not broadcast)."""
        for sid in list(session_ids):
            send_fn = self._connection_manager.get_text_sender(sid)
            if send_fn is None:
                continue
            try:
                await send_fn(json_str)
            except Exception:
                logger.debug("Failed to send JSON to session %s", sid)

    async def _send_binary_to_sessions(
        self, session_ids: set[str], data: bytes,
    ) -> None:
        """Send binary audio data to specific sessions."""
        for sid in list(session_ids):
            send_fn = self._connection_manager.get_binary_sender(sid)
            if send_fn is None:
                continue
            try:
                await send_fn(data)
            except Exception:
                logger.debug("Failed to send audio to session %s", sid)

    async def stop(self) -> None:
        """Stop the service — interrupts any in-progress TTS."""
        self._stopped = True
