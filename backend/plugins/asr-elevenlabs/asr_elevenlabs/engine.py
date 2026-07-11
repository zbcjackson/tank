"""ElevenLabs realtime streaming ASR engine.

Uses the ElevenLabs WebSocket STT API (scribe_v2_realtime) with the *manual*
commit strategy: the pipeline's VAD owns turn boundaries, so this engine does
not run its own server-side VAD. A background asyncio loop maintains the
WebSocket; the synchronous ``process_pcm`` interface bridges into it.

Connection lifecycle (lazy connect + idle close):
  * No socket is opened until the first session ``start()``.
  * The socket is kept warm across back-to-back turns in a conversation.
  * After ``idle_close_secs`` with no active session, the socket is closed and
    reopened lazily on the next ``start()``. This avoids the idle re-connect
    churn (and idle billing) that a permanently-open socket incurs, since
    ElevenLabs drops idle realtime sessions.

Endpointing: on ``stop()`` the engine sends a final chunk with ``commit: true``
to force ElevenLabs to flush a ``committed_transcript``, then waits (bounded)
for it — a real handshake rather than a fixed sleep.

Note: the engine holds a single shared WebSocket — ``create_stream()`` returns
a thin stream that routes to it. Concurrent utterances race on the same
connection.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import time

import numpy as np
import websockets
from tank_contracts import ASREngine, ASRStream

logger = logging.getLogger("ElevenLabsASR")

WS_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
MODEL_ID = "scribe_v2_realtime"

# How long to wait for the socket to come up when a session starts.
_CONNECT_TIMEOUT_S = 5.0
# How long stop() waits for the forced commit to flush a final transcript.
# Kept under the ASRProcessor's 5s stop timeout.
_FINALIZE_TIMEOUT_S = 2.0
# Default idle window before the warm socket is closed.
_DEFAULT_IDLE_CLOSE_S = 30.0


class _ElevenLabsASRStream(ASRStream):
    """Per-utterance view over the shared ElevenLabs connection."""

    def __init__(self, engine: ElevenLabsASREngine) -> None:
        self._engine = engine

    def start(self) -> None:
        self._engine._start_session()

    def process_pcm(self, pcm: np.ndarray) -> str:
        return self._engine._process_pcm(pcm)

    def stop(self) -> str:
        return self._engine._stop_session()

    def close(self) -> None:  # no per-session resources
        pass


class ElevenLabsASREngine(ASREngine):
    """Streaming ASR using the ElevenLabs realtime WebSocket API.

    Maintains a background event loop that opens the WebSocket on demand and
    closes it after an idle period. Audio chunks are sent via the stream's
    ``process_pcm``; transcripts arrive asynchronously and are buffered for the
    caller to consume.
    """

    def __init__(
        self,
        api_key: str,
        language_code: str = "",
        sample_rate: int = 16000,
        idle_close_secs: float = _DEFAULT_IDLE_CLOSE_S,
    ) -> None:
        self._api_key = api_key
        self._language_code = language_code
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

        # Set once the background loop has created its asyncio primitives, so
        # start() called immediately after construction doesn't race the loop.
        self._loop_ready = threading.Event()
        # asyncio.Event (created in the loop) that requests a connection.
        self._connect_request: asyncio.Event | None = None
        # Set by the receive loop when a committed_transcript arrives.
        self._commit_done = threading.Event()

        # Session state
        self._session_active = False
        # Monotonic timestamp of the last session activity, for idle close.
        self._last_activity = time.monotonic()

        self._start_background_loop()

    # ------------------------------------------------------------------
    # ASREngine contract
    # ------------------------------------------------------------------

    def create_stream(self) -> ASRStream:
        return _ElevenLabsASRStream(self)

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
            target=self._run_loop, daemon=True, name="elevenlabs-asr"
        )
        self._thread.start()
        # Wait until the loop's asyncio primitives exist so start() is safe.
        if not self._loop_ready.wait(timeout=5):
            logger.warning("ElevenLabs ASR: background loop failed to start")

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._connect_request = asyncio.Event()
        self._loop_ready.set()
        try:
            self._loop.run_until_complete(self._ws_lifecycle())
        except Exception:
            logger.exception("ElevenLabs ASR background loop crashed")
        finally:
            self._loop.close()

    async def _ws_lifecycle(self) -> None:
        """Wait for a connect request, connect, receive, then idle-close.

        Loops for the life of the engine: each iteration serves one warm
        connection that lives until an idle timeout or a network error.
        """
        assert self._connect_request is not None
        while self._running:
            await self._connect_request.wait()
            self._connect_request.clear()
            if not self._running:
                break
            try:
                await self._connect_and_receive()
            except Exception:
                logger.exception("ElevenLabs ASR WebSocket error")
                self._connected.clear()
                self._commit_done.set()  # unblock any waiting stop()

    async def _connect_and_receive(self) -> None:
        params = f"model_id={MODEL_ID}&sample_rate={self._sample_rate}"
        # Manual commit: the pipeline VAD owns turn boundaries. stop() forces
        # a commit explicitly, so we must not run a competing server-side VAD.
        params += "&commit_strategy=manual"
        if self._language_code:
            params += f"&language_code={self._language_code}"

        url = f"{WS_URL}?{params}"
        headers = {"xi-api-key": self._api_key}

        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            self._connected.set()
            logger.info("ElevenLabs ASR: WebSocket connected")

            idle_task = asyncio.create_task(self._idle_watchdog(ws))
            try:
                async for raw in ws:
                    self._handle_message(json.loads(raw))
            finally:
                idle_task.cancel()

        # Connection closed
        self._ws = None
        self._connected.clear()
        logger.info("ElevenLabs ASR: WebSocket closed")

    async def _idle_watchdog(self, ws: websockets.ClientConnection) -> None:
        """Close the socket after ``idle_close_secs`` with no active session."""
        while self._running:
            await asyncio.sleep(1.0)
            if self._session_active:
                continue
            if time.monotonic() - self._last_activity > self._idle_close_secs:
                logger.info("ElevenLabs ASR: idle timeout, closing socket")
                await ws.close()
                return

    def _handle_message(self, msg: dict) -> None:
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
            with self._lock:
                if text:
                    self._committed_text = text
                self._partial_text = ""
            # Unblock stop() regardless of text — the commit we asked for
            # has flushed (an empty commit means genuine silence).
            self._commit_done.set()

        elif msg_type == "input_error":
            logger.warning("ElevenLabs ASR input error: %s", msg.get("message"))
            # A rejected commit would otherwise hang stop() until timeout.
            self._commit_done.set()

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
        self._commit_done.clear()
        self._session_active = True
        self._last_activity = time.monotonic()

        if not self._connected.is_set():
            self._request_connect()
            if not self._connected.wait(timeout=_CONNECT_TIMEOUT_S):
                logger.warning("ElevenLabs ASR: connect timed out at session start")
        logger.debug("ElevenLabs: Session started")

    def _process_pcm(self, pcm: np.ndarray) -> str:
        """Send a PCM chunk to ElevenLabs and return current transcript."""
        if not self._session_active:
            logger.warning("ElevenLabs: process_pcm called without active session")
            return ""

        self._last_activity = time.monotonic()

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
            return self._partial_text or self._committed_text

    def _stop_session(self) -> str:
        """Stop the session and return the final transcript.

        Forces a commit and waits (bounded) for ElevenLabs to flush the
        committed transcript, rather than sleeping and hoping.
        """
        if not self._session_active:
            logger.warning("ElevenLabs: stop called without active session")
            return ""

        self._session_active = False
        self._last_activity = time.monotonic()

        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None:
            # Force a commit: an audio chunk with commit=true flushes a
            # committed_transcript for everything accumulated this turn.
            self._commit_done.clear()
            payload = json.dumps({
                "message_type": "input_audio_chunk",
                "audio_base_64": "",
                "commit": True,
                "sample_rate": self._sample_rate,
            })
            asyncio.run_coroutine_threadsafe(ws.send(payload), loop)
            # Wait for the committed_transcript (or an input_error) to land.
            if not self._commit_done.wait(timeout=_FINALIZE_TIMEOUT_S):
                logger.warning("ElevenLabs: commit did not flush in time")

        with self._lock:
            final_text = self._committed_text or self._partial_text
            self._committed_text = ""
            self._partial_text = ""

        logger.debug(
            "ElevenLabs: Session stopped, final text: %s",
            final_text[:50] if final_text else "(empty)",
        )
        return final_text

    def close(self) -> None:
        """Shut down the background loop and WebSocket."""
        self._session_active = False

        if not self._running:
            return
        self._running = False
        self._commit_done.set()  # unblock any waiting stop()

        loop = self._loop
        ws = self._ws
        if loop is not None:
            # Wake the lifecycle loop so it observes _running == False.
            req = self._connect_request
            if req is not None:
                loop.call_soon_threadsafe(req.set)
            if ws is not None:
                asyncio.run_coroutine_threadsafe(ws.close(), loop)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._ws = None
        self._loop = None
        logger.info("ElevenLabs: Engine closed")
