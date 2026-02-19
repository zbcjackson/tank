"""WebSocket client for connecting to the Tank backend."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Callable, Optional

import websockets

from ..schemas import WebsocketMessage, MessageType

logger = logging.getLogger("TankClient")


class TankClient:
    """
    Connects to the backend WebSocket, sends audio/text, receives messages/audio.

    Mirrors VoiceAssistantClient from frontend/src/services/websocket.ts.
    """

    def __init__(
        self,
        base_url: str = "localhost:8000",
        session_id: Optional[str] = None,
    ):
        self._session_id = session_id or uuid.uuid4().hex[:8]
        self._url = f"ws://{base_url}/ws/{self._session_id}"
        self._ws: Optional[websockets.ClientConnection] = None
        self._on_text_message: Optional[Callable[[WebsocketMessage], None]] = None
        self._on_audio_chunk: Optional[Callable[[bytes], None]] = None
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
                    if self._on_audio_chunk:
                        self._on_audio_chunk(message)
                elif isinstance(message, str):
                    msg = WebsocketMessage.model_validate_json(message)
                    if self._on_text_message:
                        self._on_text_message(msg)
        except websockets.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error("WebSocket receive error: %s", e)
        finally:
            self._running = False

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Send raw PCM audio bytes to backend."""
        if self._ws and self._running:
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
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("Disconnected")
