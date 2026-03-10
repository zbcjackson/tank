"""ElevenLabs realtime streaming ASR engine.

Uses the ElevenLabs WebSocket STT API (scribe_v2_realtime) with VAD-based
commit strategy. A background asyncio loop maintains the persistent WebSocket
connection; the synchronous ``process_pcm`` interface bridges into it.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading

import numpy as np
import websockets

from tank_contracts import StreamingASREngine

logger = logging.getLogger("ElevenLabsASR")

WS_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
MODEL_ID = "scribe_v2_realtime"


class ElevenLabsASREngine(StreamingASREngine):
    """Streaming ASR using ElevenLabs realtime WebSocket API.

    Maintains a background event loop with a persistent WebSocket connection.
    Audio chunks are sent via ``process_pcm``; transcripts arrive asynchronously
    and are buffered for the caller to consume.
    """

    def __init__(
        self,
        api_key: str,
        language_code: str = "",
        sample_rate: int = 16000,
    ) -> None:
        self._api_key = api_key
        self._language_code = language_code
        self._sample_rate = sample_rate

        # Latest transcript state (updated from WS receive loop)
        self._partial_text = ""
        self._committed_text = ""
        self._has_endpoint = False
        self._lock = threading.Lock()

        # Background event loop for the WebSocket
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = threading.Event()
        self._running = False

        self._start_background_loop()

    # ------------------------------------------------------------------
    # Background event loop
    # ------------------------------------------------------------------

    def _start_background_loop(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="elevenlabs-asr"
        )
        self._thread.start()
        # Wait for the connection to be established (up to 10s)
        if not self._connected.wait(timeout=10):
            logger.warning("ElevenLabs ASR: WebSocket connection timed out")

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._ws_lifecycle())
        except Exception:
            logger.exception("ElevenLabs ASR background loop crashed")
        finally:
            self._loop.close()

    async def _ws_lifecycle(self) -> None:
        """Connect, receive messages, reconnect on failure."""
        while self._running:
            try:
                await self._connect_and_receive()
            except Exception:
                logger.exception("ElevenLabs ASR WebSocket error, reconnecting in 2s")
                self._connected.clear()
                await asyncio.sleep(2)

    async def _connect_and_receive(self) -> None:
        params = f"model_id={MODEL_ID}&sample_rate={self._sample_rate}"
        params += "&commit_strategy=vad"
        params += "&vad_silence_threshold_secs=1.2"
        if self._language_code:
            params += f"&language_code={self._language_code}"

        url = f"{WS_URL}?{params}"
        headers = {"xi-api-key": self._api_key}

        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            self._connected.set()
            logger.info("ElevenLabs ASR: WebSocket connected")

            async for raw in ws:
                msg = json.loads(raw)
                msg_type = msg.get("message_type", "")

                if msg_type == "session_started":
                    logger.info("ElevenLabs ASR session started: %s", msg.get("session_id"))

                elif msg_type == "partial_transcript":
                    text = msg.get("text", "").strip()
                    with self._lock:
                        self._partial_text = text

                elif msg_type in (
                    "committed_transcript",
                    "committed_transcript_with_timestamps",
                ):
                    text = msg.get("text", "").strip()
                    if text:
                        with self._lock:
                            self._committed_text = text
                            self._has_endpoint = True
                            self._partial_text = ""

                elif msg_type == "input_error":
                    logger.warning("ElevenLabs ASR input error: %s", msg.get("message"))

        # Connection closed
        self._ws = None
        self._connected.clear()

    # ------------------------------------------------------------------
    # StreamingASREngine contract
    # ------------------------------------------------------------------

    def process_pcm(self, pcm: np.ndarray) -> tuple[str, bool]:
        """Send a PCM chunk to ElevenLabs and return current transcript state.

        Args:
            pcm: Float32 mono audio samples.

        Returns:
            (text, is_endpoint)
        """
        # Capture references to avoid TOCTOU race with the background thread
        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None:
            # Convert float32 → int16 bytes → base64
            int16_data = (pcm * 32767).astype(np.int16).tobytes()
            audio_b64 = base64.b64encode(int16_data).decode("ascii")

            payload = json.dumps({
                "message_type": "input_audio_chunk",
                "audio_base_64": audio_b64,
                "commit": False,
                "sample_rate": self._sample_rate,
            })

            # Fire-and-forget: don't block the audio thread waiting for send
            asyncio.run_coroutine_threadsafe(ws.send(payload), loop)

        # Read current state
        with self._lock:
            if self._has_endpoint:
                text = self._committed_text
                self._has_endpoint = False
                self._committed_text = ""
                return text, True
            return self._partial_text, False

    def reset(self) -> None:
        """Reset internal transcript state."""
        with self._lock:
            self._partial_text = ""
            self._committed_text = ""
            self._has_endpoint = False

    def close(self) -> None:
        """Shut down the background loop and WebSocket."""
        if not self._running:
            return
        self._running = False
        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None:
            asyncio.run_coroutine_threadsafe(ws.close(), loop)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._ws = None
        self._loop = None
