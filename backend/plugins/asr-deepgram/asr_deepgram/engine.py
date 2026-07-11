"""Deepgram Nova-3 realtime streaming ASR engine.

Uses the Deepgram WebSocket STT API (``/v1/listen``). A background asyncio loop
maintains the WebSocket connection; the synchronous ``process_pcm`` interface
bridges into it.

Connection lifecycle (lazy connect + idle close): the socket is not opened
until the first session ``start()``, is kept warm across back-to-back turns,
and is closed after ``idle_close_secs`` with no active session (reopened lazily
on the next ``start()``). This avoids idle re-connect churn and idle billing.

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

logger = logging.getLogger("DeepgramASR")

WS_URL = "wss://api.deepgram.com/v1/listen"

# How long to wait for the socket to come up when a session starts.
_CONNECT_TIMEOUT_S = 5.0
# Default idle window before the warm socket is closed.
_DEFAULT_IDLE_CLOSE_S = 30.0


class _DeepgramASRStream(ASRStream):
    """Per-utterance view over the shared Deepgram connection."""

    def __init__(self, engine: DeepgramASREngine) -> None:
        self._engine = engine

    def start(self) -> None:
        self._engine._start_session()

    def process_pcm(self, pcm: np.ndarray) -> str:
        return self._engine._process_pcm(pcm)

    def stop(self) -> str:
        return self._engine._stop_session()

    def close(self) -> None:  # no per-session resources
        pass


class DeepgramASREngine(ASREngine):
    """Streaming ASR using the Deepgram realtime WebSocket API.

    Maintains a background event loop with a persistent WebSocket connection.
    Audio chunks are sent via the stream's ``process_pcm``; transcripts arrive
    asynchronously and are buffered for the caller to consume.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "nova-3",
        language: str = "en",
        sample_rate: int = 16000,
        idle_close_secs: float = _DEFAULT_IDLE_CLOSE_S,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language
        self._sample_rate = sample_rate
        self._idle_close_secs = idle_close_secs

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

        # Set once the background loop has created its asyncio primitives.
        self._loop_ready = threading.Event()
        # asyncio.Event (created in the loop) that requests a connection.
        self._connect_request: asyncio.Event | None = None

        # Session state
        self._session_active = False
        # Monotonic timestamp of last session activity, for idle close.
        self._last_activity = time.monotonic()

        self._start_background_loop()

    # ------------------------------------------------------------------
    # ASREngine contract
    # ------------------------------------------------------------------

    def create_stream(self) -> ASRStream:
        return _DeepgramASRStream(self)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    # ------------------------------------------------------------------
    # Background event loop
    # ------------------------------------------------------------------

    def _start_background_loop(self) -> None:
        """Start the background thread. Does NOT open the socket — that
        happens lazily on the first session ``start()``."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="deepgram-asr"
        )
        self._thread.start()
        # Wait until the loop's asyncio primitives exist so start() is safe.
        if not self._loop_ready.wait(timeout=5):
            logger.warning("Deepgram ASR: background loop failed to start")

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._connect_request = asyncio.Event()
        self._loop_ready.set()
        try:
            self._loop.run_until_complete(self._ws_lifecycle())
        except Exception:
            logger.exception("Deepgram ASR background loop crashed")
        finally:
            self._loop.close()

    async def _ws_lifecycle(self) -> None:
        """Wait for a connect request, connect, receive, then idle-close."""
        assert self._connect_request is not None
        while self._running:
            await self._connect_request.wait()
            self._connect_request.clear()
            if not self._running:
                break
            try:
                await self._connect_and_receive()
            except Exception:
                logger.exception("Deepgram ASR WebSocket error")
                self._connected.clear()

    async def _connect_and_receive(self) -> None:
        params = urlencode({
            "model": self._model,
            "encoding": "linear16",
            "sample_rate": self._sample_rate,
            "channels": 1,
            "interim_results": "true",
            "smart_format": "true",
            "language": self._language,
        })

        url = f"{WS_URL}?{params}"
        headers = {"Authorization": f"Token {self._api_key}"}

        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            self._connected.set()
            logger.info("Deepgram ASR: WebSocket connected")

            idle_task = asyncio.create_task(self._idle_watchdog(ws))
            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    self._handle_message(msg)
            finally:
                idle_task.cancel()

        # Connection closed
        self._ws = None
        self._connected.clear()
        logger.info("Deepgram ASR: WebSocket closed")

    async def _idle_watchdog(self, ws: websockets.ClientConnection) -> None:
        """Close the socket after ``idle_close_secs`` with no active session."""
        while self._running:
            await asyncio.sleep(1.0)
            if self._session_active:
                continue
            if time.monotonic() - self._last_activity > self._idle_close_secs:
                logger.info("Deepgram ASR: idle timeout, closing socket")
                await ws.close()
                return

    def _handle_message(self, msg: dict) -> None:
        """Parse a Deepgram ``Results`` message and update transcript state."""
        if msg.get("type") != "Results":
            return

        channel = msg.get("channel", {})
        alternatives = channel.get("alternatives", [])
        if not alternatives:
            return

        text = alternatives[0].get("transcript", "").strip()
        if not text:
            return

        if msg.get("is_final"):
            with self._lock:
                # Accumulate finalized segments across the utterance.
                self._committed_text = (
                    f"{self._committed_text} {text}".strip()
                    if self._committed_text
                    else text
                )
                self._partial_text = ""
        else:
            with self._lock:
                self._partial_text = text

    # ------------------------------------------------------------------
    # Session helpers (called by the per-stream wrapper)
    # ------------------------------------------------------------------

    def _request_connect(self) -> None:
        """Ask the background loop to open a connection (thread-safe)."""
        loop = self._loop
        req = self._connect_request
        if loop is not None and req is not None:
            loop.call_soon_threadsafe(req.set)

    def _start_session(self) -> None:
        """Start a new recognition session, connecting the socket if needed."""
        with self._lock:
            self._partial_text = ""
            self._committed_text = ""
        self._session_active = True
        self._last_activity = time.monotonic()

        if not self._connected.is_set():
            self._request_connect()
            if not self._connected.wait(timeout=_CONNECT_TIMEOUT_S):
                logger.warning("Deepgram ASR: connect timed out at session start")
        logger.debug("Deepgram: Session started")

    def _process_pcm(self, pcm: np.ndarray) -> str:
        """Send a PCM chunk to Deepgram and return current transcript."""
        if not self._session_active:
            logger.warning("Deepgram: process_pcm called without active session")
            return ""

        self._last_activity = time.monotonic()

        # Capture references to avoid TOCTOU race with the background thread
        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None:
            # Convert float32 → int16 raw bytes (linear16)
            int16_data = (pcm * 32767).astype(np.int16).tobytes()

            # Fire-and-forget: don't block the audio thread waiting for send
            asyncio.run_coroutine_threadsafe(ws.send(int16_data), loop)

        # Read current state
        with self._lock:
            committed = self._committed_text
            partial = self._partial_text
            return f"{committed} {partial}".strip() if partial else committed

    def _stop_session(self) -> str:
        """Stop the session and return final transcript."""
        if not self._session_active:
            logger.warning("Deepgram: stop called without active session")
            return ""

        self._session_active = False
        self._last_activity = time.monotonic()

        # Ask Deepgram to flush any buffered audio into a final result.
        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None:
            asyncio.run_coroutine_threadsafe(
                ws.send(json.dumps({"type": "Finalize"})), loop
            )

        # Wait briefly for any pending transcripts
        time.sleep(0.2)

        with self._lock:
            final_text = (
                f"{self._committed_text} {self._partial_text}".strip()
                if self._partial_text
                else self._committed_text
            )
            self._committed_text = ""
            self._partial_text = ""

        logger.debug(
            "Deepgram: Session stopped, final text: %s",
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
        if loop is not None:
            # Wake the lifecycle loop so it observes _running == False.
            req = self._connect_request
            if req is not None:
                loop.call_soon_threadsafe(req.set)
            if ws is not None:
                # CloseStream tells Deepgram to finish and close gracefully.
                asyncio.run_coroutine_threadsafe(
                    ws.send(json.dumps({"type": "CloseStream"})), loop
                )
                asyncio.run_coroutine_threadsafe(ws.close(), loop)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._ws = None
        self._loop = None
        logger.info("Deepgram: Engine closed")
