"""WebSocket client for connecting to the Tank backend."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

import websockets
from tank_protocol import MessageType, WebsocketMessage

from ..audio.frame import encode_audio_frame
from ..audio.opus_codec import (
    DOWNLINK_SAMPLE_RATE,
    OPUS_AVAILABLE,
    ClientCodecs,
    OpusDecodeError,
    create_client_codecs,
)

logger = logging.getLogger("TankClient")


class TankClient:
    """
    Connects to the backend WebSocket, sends audio/text, receives messages/audio.

    Mirrors VoiceAssistantClient from frontend/src/services/websocket.ts.

    Protocol negotiation (P1-2): when ``signal: ready`` advertises ``opus``,
    declares it and switches binary audio to one Opus packet per message,
    both directions, on the ``signal: capabilities`` ack. Undecodable
    downlink packets are warn-and-dropped.
    """

    def __init__(
        self,
        base_url: str = "localhost:8000",
        session_id: str | None = None,
    ):
        self._session_id = session_id or uuid.uuid4().hex[:8]
        self._url = f"ws://{base_url}/ws/{self._session_id}"
        self._ws: websockets.ClientConnection | None = None
        self._on_text_message: Callable[[WebsocketMessage], None] | None = None
        self._on_audio_chunk: Callable[[bytes], None] | None = None
        self._codecs: ClientCodecs | None = None
        self._declared = False
        self._running = False

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_connected(self) -> bool:
        return self._running and self._ws is not None

    async def connect(
        self,
        on_text_message: Callable[[WebsocketMessage], None],
        on_audio_chunk: Callable[[bytes], None],
    ) -> None:
        """Connect to the backend WebSocket server."""
        self._on_text_message = on_text_message
        self._on_audio_chunk = on_audio_chunk
        self._ws = await websockets.connect(self._url)
        self._running = True
        logger.info("Connected to %s", self._url)

    async def receive_loop(self) -> None:
        """Main receive loop — run as asyncio task."""
        if self._ws is None:
            return
        try:
            async for message in self._ws:
                if not self._running:
                    break
                if isinstance(message, bytes):
                    self._on_binary(message)
                elif isinstance(message, str):
                    msg = WebsocketMessage.model_validate_json(message)
                    await self._handle_handshake(msg)
                    if self._on_text_message:
                        self._on_text_message(msg)
        except websockets.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error("WebSocket receive error: %s", e)
        finally:
            self._running = False

    async def _handle_handshake(self, msg: WebsocketMessage) -> None:
        """Opus negotiation: declare on ``ready``, switch codecs on the ack.

        Between the server processing our declaration and the ack arriving,
        uplink PCM can hit the server's opus decoder and be dropped — the
        connect-time race the protocol plan accepted (no user speech yet).
        """
        if msg.type != MessageType.SIGNAL:
            return
        metadata = msg.metadata or {}
        if msg.content == "ready":
            features = metadata.get("protocol_features", [])
            if (
                isinstance(features, list)
                and "opus" in features
                and not self._declared
                and OPUS_AVAILABLE
            ):
                declaration = WebsocketMessage(
                    type=MessageType.SIGNAL,
                    content="capabilities",
                    metadata={"enable": ["opus"]},
                )
                if self._ws and self._running:
                    await self._ws.send(declaration.model_dump_json())
                    self._declared = True
                    logger.info("Declared opus capability")
        elif msg.content == "capabilities":
            enabled = metadata.get("enabled", [])
            if isinstance(enabled, list) and "opus" in enabled and self._codecs is None:
                self._codecs = create_client_codecs()
                logger.info("Opus negotiated — binary audio switched to opus")

    def _on_binary(self, message: bytes) -> None:
        """Binary frame → on_audio_chunk, decoding opus first when negotiated."""
        if self._codecs is not None:
            try:
                pcm = self._codecs.downlink.decode_packet(message)
            except OpusDecodeError as e:
                logger.warning("Dropping undecodable opus packet: %s", e)
                return
            frame = encode_audio_frame(pcm, DOWNLINK_SAMPLE_RATE, 1)
        else:
            frame = message
        if self._on_audio_chunk:
            self._on_audio_chunk(frame)

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Send mic PCM16 bytes; re-buffers into opus packets when negotiated."""
        if self._ws and self._running:
            if self._codecs is not None:
                for packet in self._codecs.uplink.feed(pcm_bytes):
                    await self._ws.send(packet)
            else:
                await self._ws.send(pcm_bytes)

    async def send_text_input(self, text: str) -> None:
        """Send keyboard text input."""
        msg = WebsocketMessage(type=MessageType.INPUT, content=text)
        if self._ws and self._running:
            await self._ws.send(msg.model_dump_json())

    async def send_interrupt(self) -> None:
        """Send interrupt signal to stop current TTS/LLM processing."""
        msg = WebsocketMessage(type=MessageType.SIGNAL, content="interrupt")
        if self._ws and self._running:
            await self._ws.send(msg.model_dump_json())

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        self._running = False
        self._codecs = None
        self._declared = False
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("Disconnected")
