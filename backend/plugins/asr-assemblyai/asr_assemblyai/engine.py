"""AssemblyAI Universal-Streaming realtime ASR engine.

Uses the AssemblyAI v3 streaming WebSocket API
(``wss://streaming.assemblyai.com/v3/ws``). A background asyncio loop maintains
the persistent WebSocket connection; the synchronous ``process_pcm`` interface
bridges into it.

Note: the engine holds a single shared WebSocket — ``create_stream()`` returns
a thin stream that routes to it. Concurrent utterances race on the same
connection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from urllib.parse import urlencode

import numpy as np
import websockets
from tank_contracts import ASREngine, ASRStream

logger = logging.getLogger("AssemblyAIASR")

WS_URL = "wss://streaming.assemblyai.com/v3/ws"


class _AssemblyAIASRStream(ASRStream):
    """Per-utterance view over the shared AssemblyAI connection."""

    def __init__(self, engine: AssemblyAIASREngine) -> None:
        self._engine = engine

    def start(self) -> None:
        self._engine._start_session()

    def process_pcm(self, pcm: np.ndarray) -> str:
        return self._engine._process_pcm(pcm)

    def stop(self) -> str:
        return self._engine._stop_session()

    def close(self) -> None:  # no per-session resources
        pass


class AssemblyAIASREngine(ASREngine):
    """Streaming ASR using the AssemblyAI Universal-Streaming WebSocket API.

    Maintains a background event loop with a persistent WebSocket connection.
    Audio chunks are sent via the stream's ``process_pcm``; transcripts arrive
    asynchronously and are buffered for the caller to consume.
    """

    def __init__(
        self,
        api_key: str,
        speech_model: str = "universal-3-5-pro",
        sample_rate: int = 16000,
    ) -> None:
        self._api_key = api_key
        self._speech_model = speech_model
        self._sample_rate = sample_rate

        # Latest transcript state (updated from WS receive loop)
        self._partial_text = ""
        self._committed_text = ""
        self._lock = threading.Lock()

        # Background event loop for the WebSocket
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ws: websockets.ClientConnection | None = None
        self._connected = threading.Event()
        self._running = False

        # Session state
        self._session_active = False

        self._start_background_loop()

    # ------------------------------------------------------------------
    # ASREngine contract
    # ------------------------------------------------------------------

    def create_stream(self) -> ASRStream:
        return _AssemblyAIASRStream(self)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    # ------------------------------------------------------------------
    # Background event loop
    # ------------------------------------------------------------------

    def _start_background_loop(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="assemblyai-asr"
        )
        self._thread.start()
        # Wait for the connection to be established (up to 10s)
        if not self._connected.wait(timeout=10):
            logger.warning("AssemblyAI ASR: WebSocket connection timed out")

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._ws_lifecycle())
        except Exception:
            logger.exception("AssemblyAI ASR background loop crashed")
        finally:
            self._loop.close()

    async def _ws_lifecycle(self) -> None:
        """Connect, receive messages, reconnect on failure."""
        while self._running:
            try:
                await self._connect_and_receive()
            except Exception:
                logger.exception("AssemblyAI ASR WebSocket error, reconnecting in 2s")
                self._connected.clear()
                await asyncio.sleep(2)

    async def _connect_and_receive(self) -> None:
        params = urlencode({
            "sample_rate": self._sample_rate,
            "speech_model": self._speech_model,
        })

        url = f"{WS_URL}?{params}"
        # AssemblyAI takes the raw API key with no "Token"/"Bearer" prefix.
        headers = {"Authorization": self._api_key}

        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            self._connected.set()
            logger.info("AssemblyAI ASR: WebSocket connected")

            async for raw in ws:
                msg = json.loads(raw)
                self._handle_message(msg)

        # Connection closed
        self._ws = None
        self._connected.clear()

    def _handle_message(self, msg: dict) -> None:
        """Parse an AssemblyAI ``Turn`` message and update transcript state."""
        msg_type = msg.get("type", "")

        if msg_type == "Begin":
            logger.info("AssemblyAI ASR session started: %s", msg.get("id"))
            return

        if msg_type != "Turn":
            return

        text = msg.get("transcript", "").strip()
        if not text:
            return

        if msg.get("end_of_turn"):
            with self._lock:
                self._committed_text = text
                self._partial_text = ""
        else:
            with self._lock:
                self._partial_text = text

    # ------------------------------------------------------------------
    # Session helpers (called by the per-stream wrapper)
    # ------------------------------------------------------------------

    def _start_session(self) -> None:
        """Start a new recognition session."""
        with self._lock:
            self._partial_text = ""
            self._committed_text = ""
        self._session_active = True
        logger.debug("AssemblyAI: Session started")

    def _process_pcm(self, pcm: np.ndarray) -> str:
        """Send a PCM chunk to AssemblyAI and return current transcript."""
        if not self._session_active:
            logger.warning("AssemblyAI: process_pcm called without active session")
            return ""

        # Capture references to avoid TOCTOU race with the background thread
        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None:
            # Convert float32 → int16 raw bytes (mono 16-bit PCM)
            int16_data = (pcm * 32767).astype(np.int16).tobytes()

            # Fire-and-forget: don't block the audio thread waiting for send
            asyncio.run_coroutine_threadsafe(ws.send(int16_data), loop)

        # Read current state
        with self._lock:
            return self._committed_text or self._partial_text

    def _stop_session(self) -> str:
        """Stop the session and return final transcript."""
        if not self._session_active:
            logger.warning("AssemblyAI: stop called without active session")
            return ""

        self._session_active = False

        # Wait briefly for any pending end_of_turn transcript
        time.sleep(0.2)

        with self._lock:
            final_text = self._committed_text or self._partial_text
            self._committed_text = ""
            self._partial_text = ""

        logger.debug(
            "AssemblyAI: Session stopped, final text: %s",
            final_text[:50] if final_text else "(empty)",
        )
        return final_text

    def close(self) -> None:
        """Shut down the background loop and WebSocket."""
        self._session_active = False

        if not self._running:
            return
        self._running = False
        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None:
            # Terminate tells AssemblyAI to end the billed session cleanly.
            asyncio.run_coroutine_threadsafe(
                ws.send(json.dumps({"type": "Terminate"})), loop
            )
            asyncio.run_coroutine_threadsafe(ws.close(), loop)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._ws = None
        self._loop = None
        logger.info("AssemblyAI: Engine closed")
