"""FunASR streaming ASR engine.

Supports two protocols via a single ``StreamingASREngine`` implementation:

**Self-hosted FunASR** (no ``api_key``):
  1. Client sends JSON config (mode, sample_rate, chunk_size, etc.)
  2. Client streams raw Int16 PCM as binary WebSocket frames
  3. Server returns JSON with partial/final transcripts
  4. Client sends ``{"is_speaking": false}`` to signal end-of-utterance

**DashScope cloud** (``api_key`` provided):
  Uses the official DashScope SDK (dashscope.audio.asr.Recognition) for
  real-time streaming ASR. The SDK handles all WebSocket protocol details.

Protocol is auto-detected: if ``api_key`` is set, DashScope SDK is used.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

import numpy as np
import websockets

from tank_contracts import StreamingASREngine

logger = logging.getLogger("FunASR")

# Default chunk_interval used by self-hosted FunASR for stride calculation.
_CHUNK_INTERVAL = 10

# DashScope default model
_DASHSCOPE_DEFAULT_MODEL = "paraformer-realtime-v2"


class FunASREngine(StreamingASREngine):
    """Streaming ASR using FunASR WebSocket API or DashScope SDK.

    When ``api_key`` is provided, uses DashScope SDK (recommended).
    Otherwise, connects to a self-hosted FunASR server via WebSocket.

    Lifecycle:
        start()      - Start recognition session
        process_pcm() - Stream audio chunks
        stop()       - Stop session and get final transcript
        close()      - Release all resources
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: str = "10095",
        mode: str = "2pass",
        is_ssl: bool = False,
        sample_rate: int = 16000,
        chunk_size: list[int] | None = None,
        hotwords: dict[str, int] | None = None,
        itn: bool = True,
        api_key: str = "",
        model: str = "",
        dashscope_url: str = "",
    ) -> None:
        self._host = host
        self._port = port
        self._mode = mode
        self._is_ssl = is_ssl
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size or [5, 10, 5]
        self._hotwords = hotwords or {}
        self._itn = itn

        # DashScope-specific
        self._api_key = api_key
        self._model = model or _DASHSCOPE_DEFAULT_MODEL
        self._dashscope_url = dashscope_url
        self._is_dashscope = bool(api_key)

        # Latest transcript state
        self._partial_text = ""
        self._committed_text = ""
        self._lock = threading.Lock()

        # Audio accumulator
        self._audio_buffer = bytearray()

        # Session state
        self._session_active = False

        if self._is_dashscope:
            self._init_dashscope()
        else:
            self._init_funasr_websocket()

    # ------------------------------------------------------------------
    # DashScope SDK implementation
    # ------------------------------------------------------------------

    def _init_dashscope(self) -> None:
        """Initialize DashScope SDK state."""
        import dashscope
        from dashscope.audio.asr import RecognitionCallback

        # Configure API key
        dashscope.api_key = self._api_key
        if self._dashscope_url:
            dashscope.base_http_api_url = self._dashscope_url

        self._recognition: Any = None
        self._recognition_started = False
        self._recognition_closed = True
        self._restart_lock = threading.Lock()

        # Create callback handler
        engine = self

        class _Callback(RecognitionCallback):
            def on_open(self) -> None:
                logger.info("DashScope: Recognition opened")
                with engine._lock:
                    engine._recognition_closed = False

            def on_close(self) -> None:
                logger.info("DashScope: Recognition closed")
                with engine._lock:
                    engine._recognition_closed = True
                    engine._recognition_started = False

            def on_complete(self) -> None:
                logger.info("DashScope: Recognition complete")
                with engine._lock:
                    engine._recognition_closed = True
                    engine._recognition_started = False

            def on_error(self, result) -> None:  # type: ignore[override]
                logger.error(
                    "DashScope: Recognition error: %s - %s",
                    result.code,
                    result.message,
                )
                with engine._lock:
                    engine._recognition_closed = True
                    engine._recognition_started = False

            def on_event(self, result) -> None:  # type: ignore[override]
                engine._handle_dashscope_result(result)

        self._callback = _Callback()
        logger.info("DashScope: Initialized")

    def _start_dashscope_recognition(self) -> None:
        """Start a new DashScope recognition session."""
        from dashscope.audio.asr import Recognition

        with self._restart_lock:
            if self._recognition_started and not self._recognition_closed:
                return

            self._recognition = Recognition(
                model=self._model,
                callback=self._callback,
                format="pcm",
                sample_rate=self._sample_rate,
                language_hints=["zh", "en"],
                punctuation_prediction_enabled=True,
                inverse_text_normalization_enabled=self._itn,
            )

            try:
                self._recognition.start()
                with self._lock:
                    self._recognition_started = True
                    self._recognition_closed = False
                logger.info("DashScope: Recognition started with model=%s", self._model)
            except Exception:
                logger.exception("DashScope: Failed to start recognition")
                with self._lock:
                    self._recognition_started = False

    def _stop_dashscope_recognition(self) -> str:
        """Stop DashScope recognition and return final transcript."""
        # Flush remaining audio
        if self._recognition is not None and self._recognition_started:
            remaining = bytes(self._audio_buffer)
            self._audio_buffer = bytearray()
            if remaining:
                try:
                    self._recognition.send_audio_frame(remaining)
                except Exception:
                    pass

            # Stop recognition
            try:
                self._recognition.stop()
                logger.debug("DashScope: Recognition stopped")
            except Exception:
                pass

        # Wait briefly for final results
        time.sleep(0.1)

        with self._lock:
            self._recognition_started = False
            self._recognition_closed = True
            self._recognition = None
            # Return best available text
            final_text = self._committed_text or self._partial_text
            self._committed_text = ""
            self._partial_text = ""
            return final_text

    def _handle_dashscope_result(self, result: Any) -> None:
        """Handle DashScope recognition result."""
        from dashscope.audio.asr import RecognitionResult

        sentence = result.get_sentence()
        if sentence is None:
            return

        text = sentence.get("text", "").strip()
        is_end = RecognitionResult.is_sentence_end(sentence)

        with self._lock:
            if is_end:
                if text:
                    self._committed_text = text
                    self._partial_text = ""
            else:
                self._partial_text = text

    def _process_dashscope(self, int16_data: bytes) -> None:
        """Send audio data to DashScope SDK."""
        if self._recognition is None or not self._recognition_started:
            logger.warning("DashScope: Recognition not started, dropping audio")
            return

        # Accumulate and send in ~100ms chunks (3200 bytes at 16kHz/16bit)
        send_stride = int(self._sample_rate * 0.1) * 2
        self._audio_buffer.extend(int16_data)

        while len(self._audio_buffer) >= send_stride:
            chunk = bytes(self._audio_buffer[:send_stride])
            self._audio_buffer = self._audio_buffer[send_stride:]
            try:
                self._recognition.send_audio_frame(chunk)
            except Exception as e:
                if "stopped" in str(e).lower():
                    logger.debug("DashScope: Recognition stopped unexpectedly")
                    with self._lock:
                        self._recognition_closed = True
                        self._recognition_started = False
                    self._audio_buffer = bytearray(chunk) + self._audio_buffer
                    break
                else:
                    logger.exception("DashScope: Failed to send audio frame")
                    break

    def _close_dashscope(self) -> None:
        """Close DashScope recognition."""
        if self._recognition is not None:
            with self._lock:
                was_running = self._recognition_started and not self._recognition_closed
            if was_running:
                try:
                    self._recognition.stop()
                except Exception:
                    pass
            with self._lock:
                self._recognition_started = False
                self._recognition_closed = True
        self._recognition = None

    # ------------------------------------------------------------------
    # Self-hosted FunASR WebSocket implementation
    # ------------------------------------------------------------------

    def _init_funasr_websocket(self) -> None:
        """Initialize self-hosted FunASR WebSocket connection."""
        self._send_stride = int(
            60 * self._chunk_size[1] / _CHUNK_INTERVAL / 1000
            * self._sample_rate * 2
        )

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = threading.Event()
        self._running = False
        self._config_sent = False

        self._start_background_loop()

    def _start_background_loop(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="funasr-asr",
        )
        self._thread.start()
        if not self._connected.wait(timeout=10):
            logger.warning("FunASR: WebSocket connection timed out")

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._ws_lifecycle())
        except Exception:
            logger.exception("FunASR background loop crashed")
        finally:
            self._loop.close()

    async def _ws_lifecycle(self) -> None:
        while self._running:
            try:
                await self._connect_and_receive()
            except Exception:
                logger.exception("FunASR WebSocket error, reconnecting in 2s")
                self._connected.clear()
                self._config_sent = False
                await asyncio.sleep(2)

    def _build_url(self) -> str:
        scheme = "wss" if self._is_ssl else "ws"
        return f"{scheme}://{self._host}:{self._port}"

    async def _connect_and_receive(self) -> None:
        url = self._build_url()

        async with websockets.connect(url) as ws:
            self._ws = ws
            self._connected.set()
            self._config_sent = False
            logger.info("FunASR: WebSocket connected to %s", url)

            async for raw in ws:
                self._handle_funasr_message(raw)

        self._ws = None
        self._connected.clear()
        self._config_sent = False

    async def _send_funasr_config(self, ws: websockets.WebSocketClientProtocol) -> None:
        config: dict = {
            "mode": self._mode,
            "wav_name": "tank-stream",
            "is_speaking": True,
            "wav_format": "pcm",
            "audio_fs": self._sample_rate,
            "chunk_size": self._chunk_size,
            "itn": self._itn,
        }
        if self._hotwords:
            config["hotwords"] = json.dumps(self._hotwords)

        await ws.send(json.dumps(config))
        self._config_sent = True
        logger.debug("FunASR: config sent: mode=%s", self._mode)

    def _handle_funasr_message(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("FunASR: unparseable server message")
            return

        mode = msg.get("mode", "")
        text = msg.get("text", "").strip()
        is_final = msg.get("is_final", False)

        with self._lock:
            if mode.endswith("-online"):
                self._partial_text = text
            elif mode.endswith("-offline") or mode == "offline":
                if text:
                    self._committed_text = text
                    self._partial_text = ""
            elif mode == "online":
                if is_final:
                    if text:
                        self._committed_text = text
                        self._partial_text = ""
                else:
                    self._partial_text = text
            else:
                if text:
                    self._partial_text = text

    def _start_funasr_session(self) -> None:
        """Start a FunASR session by sending config."""
        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None and not self._config_sent:
            asyncio.run_coroutine_threadsafe(self._send_funasr_config(ws), loop)

    def _stop_funasr_session(self) -> str:
        """Stop FunASR session and return final transcript."""
        ws = self._ws
        loop = self._loop

        if ws is not None and loop is not None:
            # Flush remaining audio
            remaining = bytes(self._audio_buffer)
            self._audio_buffer = bytearray()
            if remaining:
                asyncio.run_coroutine_threadsafe(ws.send(remaining), loop)

            # Signal end-of-utterance
            finish_msg = json.dumps({"is_speaking": False})
            asyncio.run_coroutine_threadsafe(ws.send(finish_msg), loop)

        # Wait briefly for final results
        time.sleep(0.1)

        with self._lock:
            self._config_sent = False
            final_text = self._committed_text or self._partial_text
            self._committed_text = ""
            self._partial_text = ""
            return final_text

    def _process_funasr_ws(self, int16_data: bytes) -> None:
        ws = self._ws
        loop = self._loop
        if ws is None or loop is None or not self._config_sent:
            return

        self._audio_buffer.extend(int16_data)
        while len(self._audio_buffer) >= self._send_stride:
            chunk = bytes(self._audio_buffer[:self._send_stride])
            self._audio_buffer = self._audio_buffer[self._send_stride:]
            asyncio.run_coroutine_threadsafe(ws.send(chunk), loop)

    def _close_funasr_ws(self) -> None:
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

    # ------------------------------------------------------------------
    # StreamingASREngine contract
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start a new recognition session."""
        with self._lock:
            self._partial_text = ""
            self._committed_text = ""
            self._audio_buffer = bytearray()

        self._session_active = True

        if self._is_dashscope:
            self._start_dashscope_recognition()
        else:
            self._start_funasr_session()

        logger.debug("FunASR: Session started")

    def process_pcm(self, pcm: np.ndarray) -> str:
        """Process a chunk of PCM audio.

        Returns:
            Current partial transcript text.
        """
        if not self._session_active:
            logger.warning("FunASR: process_pcm called without active session")
            return ""

        int16_data = (pcm * 32767).astype(np.int16).tobytes()

        if self._is_dashscope:
            self._process_dashscope(int16_data)
        else:
            self._process_funasr_ws(int16_data)

        with self._lock:
            return self._partial_text or self._committed_text

    def stop(self) -> str:
        """Stop the session and return final transcript."""
        if not self._session_active:
            logger.warning("FunASR: stop called without active session")
            return ""

        self._session_active = False

        if self._is_dashscope:
            final_text = self._stop_dashscope_recognition()
        else:
            final_text = self._stop_funasr_session()

        logger.debug("FunASR: Session stopped, final text: %s", final_text[:50] if final_text else "(empty)")
        return final_text

    def close(self) -> None:
        """Release all resources."""
        self._session_active = False

        if self._is_dashscope:
            self._close_dashscope()
        else:
            self._close_funasr_ws()

        logger.info("FunASR: Engine closed")

