"""FunASR streaming ASR engine.

Supports two protocols via a single ``StreamingASREngine`` implementation:

**Self-hosted FunASR** (no ``api_key``):
  1. Client sends JSON config (mode, sample_rate, chunk_size, etc.)
  2. Client streams raw Int16 PCM as binary WebSocket frames
  3. Server returns JSON with partial/final transcripts
  4. Client sends ``{"is_speaking": false}`` to signal end-of-utterance

**DashScope cloud** (``api_key`` provided):
  1. Client connects to ``wss://dashscope.aliyuncs.com/api-ws/v1/inference``
     with ``Authorization: Bearer <key>`` header
  2. Client sends ``run-task`` JSON envelope
  3. Client streams raw Int16 PCM as binary WebSocket frames
  4. Server returns ``result-generated`` events with sentence partials/finals
  5. Client sends ``finish-task`` JSON envelope to signal end

Protocol is auto-detected: if ``api_key`` is set, DashScope is used.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid

import numpy as np
import websockets

from tank_contracts import StreamingASREngine

logger = logging.getLogger("FunASR")

# Default chunk_interval used by self-hosted FunASR for stride calculation.
_CHUNK_INTERVAL = 10

# DashScope endpoints
_DASHSCOPE_URL_CN = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
_DASHSCOPE_URL_INTL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
_DASHSCOPE_DEFAULT_MODEL = "paraformer-realtime-v2"


class FunASREngine(StreamingASREngine):
    """Streaming ASR using FunASR WebSocket API.

    Maintains a background event loop with a persistent WebSocket connection.
    Audio chunks are sent via ``process_pcm``; transcripts arrive asynchronously
    and are buffered for the caller to consume.

    When ``api_key`` is provided, connects to Alibaba DashScope cloud.
    Otherwise, connects to a self-hosted FunASR server.
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
        self._task_id = ""
        self._task_started = threading.Event()

        # Compute bytes-per-send stride from chunk_size (self-hosted mode).
        # DashScope recommends ~100ms chunks (~3200 bytes at 16kHz/16bit).
        if self._is_dashscope:
            self._send_stride = int(self._sample_rate * 0.1) * 2  # 100ms
        else:
            self._send_stride = int(
                60 * self._chunk_size[1] / _CHUNK_INTERVAL / 1000
                * self._sample_rate * 2
            )

        # Latest transcript state (updated from WS receive loop)
        self._partial_text = ""
        self._committed_text = ""
        self._has_endpoint = False
        self._lock = threading.Lock()

        # Audio accumulator — buffer partial PCM until we have a full stride
        self._audio_buffer = bytearray()

        # Background event loop for the WebSocket
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = threading.Event()
        self._running = False
        self._config_sent = False

        self._start_background_loop()

    # ------------------------------------------------------------------
    # Background event loop
    # ------------------------------------------------------------------

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
        """Connect, receive messages, reconnect on failure."""
        while self._running:
            try:
                await self._connect_and_receive()
            except Exception:
                logger.exception("FunASR WebSocket error, reconnecting in 2s")
                self._connected.clear()
                self._config_sent = False
                self._task_started.clear()
                await asyncio.sleep(2)

    # ------------------------------------------------------------------
    # Connection: protocol-aware
    # ------------------------------------------------------------------

    def _build_url(self) -> str:
        if self._is_dashscope:
            if self._dashscope_url:
                return self._dashscope_url
            return _DASHSCOPE_URL_CN
        scheme = "wss" if self._is_ssl else "ws"
        return f"{scheme}://{self._host}:{self._port}"

    def _build_headers(self) -> dict[str, str]:
        if self._is_dashscope:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def _connect_and_receive(self) -> None:
        url = self._build_url()
        headers = self._build_headers()

        async with websockets.connect(url, additional_headers=headers) as ws:
            self._ws = ws
            self._connected.set()
            self._config_sent = False
            self._task_started.clear()
            logger.info("FunASR: WebSocket connected to %s", url)

            # Send initial configuration / run-task
            await self._send_config(ws)

            async for raw in ws:
                self._handle_server_message(raw)

        # Connection closed
        self._ws = None
        self._connected.clear()
        self._config_sent = False
        self._task_started.clear()

    # ------------------------------------------------------------------
    # Config / start task
    # ------------------------------------------------------------------

    async def _send_config(self, ws: websockets.WebSocketClientProtocol) -> None:
        """Send the initial configuration frame (protocol-dependent)."""
        if self._is_dashscope:
            await self._send_dashscope_run_task(ws)
        else:
            await self._send_funasr_config(ws)

    async def _send_funasr_config(self, ws: websockets.WebSocketClientProtocol) -> None:
        """Self-hosted FunASR: flat JSON config."""
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
        logger.debug("FunASR: config sent (self-hosted): mode=%s", self._mode)

    async def _send_dashscope_run_task(self, ws: websockets.WebSocketClientProtocol) -> None:
        """DashScope: run-task envelope."""
        self._task_id = uuid.uuid4().hex
        run_task: dict = {
            "header": {
                "action": "run-task",
                "task_id": self._task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "asr",
                "function": "recognition",
                "model": self._model,
                "parameters": {
                    "format": "pcm",
                    "sample_rate": self._sample_rate,
                    "language_hints": ["zh", "en"],
                    "punctuation_prediction_enabled": True,
                    "inverse_text_normalization_enabled": self._itn,
                },
                "input": {},
            },
        }
        await ws.send(json.dumps(run_task))
        # Don't set _config_sent yet — wait for task-started event
        logger.debug("FunASR: run-task sent (DashScope): model=%s", self._model)

    # ------------------------------------------------------------------
    # Message handling: protocol-aware
    # ------------------------------------------------------------------

    def _handle_server_message(self, raw: str | bytes) -> None:
        """Parse a server response and update transcript state."""
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("FunASR: unparseable server message")
            return

        if self._is_dashscope:
            self._handle_dashscope_message(msg)
        else:
            self._handle_funasr_message(msg)

    def _handle_funasr_message(self, msg: dict) -> None:
        """Handle self-hosted FunASR response."""
        mode = msg.get("mode", "")
        text = msg.get("text", "").strip()
        is_final = msg.get("is_final", False)

        with self._lock:
            if mode.endswith("-online"):
                self._partial_text = text
            elif mode.endswith("-offline") or mode == "offline":
                if text:
                    self._committed_text = text
                    self._has_endpoint = True
                    self._partial_text = ""
            elif mode == "online":
                if is_final:
                    if text:
                        self._committed_text = text
                        self._has_endpoint = True
                        self._partial_text = ""
                else:
                    self._partial_text = text
            else:
                if text:
                    self._partial_text = text

    def _handle_dashscope_message(self, msg: dict) -> None:
        """Handle DashScope API response."""
        header = msg.get("header", {})
        event = header.get("event", "")

        if event == "task-started":
            logger.info("FunASR: DashScope task started: %s", header.get("task_id"))
            self._config_sent = True
            self._task_started.set()

        elif event == "result-generated":
            payload = msg.get("payload", {})
            output = payload.get("output", {})
            sentence = output.get("sentence", {})
            text = sentence.get("text", "").strip()
            sentence_end = sentence.get("sentence_end", False)

            with self._lock:
                if sentence_end:
                    if text:
                        self._committed_text = text
                        self._has_endpoint = True
                        self._partial_text = ""
                else:
                    self._partial_text = text

        elif event == "task-finished":
            logger.info("FunASR: DashScope task finished")

        elif event == "task-failed":
            error_code = header.get("error_code", "UNKNOWN")
            error_msg = header.get("error_message", "")
            logger.error("FunASR: DashScope task failed: %s — %s", error_code, error_msg)

    # ------------------------------------------------------------------
    # StreamingASREngine contract
    # ------------------------------------------------------------------

    def process_pcm(self, pcm: np.ndarray) -> tuple[str, bool]:
        """Send a PCM chunk to FunASR and return current transcript state.

        Args:
            pcm: Float32 mono audio samples.

        Returns:
            (text, is_endpoint)
        """
        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None and self._config_sent:
            # Convert float32 → int16 bytes
            int16_data = (pcm * 32767).astype(np.int16).tobytes()

            # Accumulate into buffer and send stride-sized chunks
            self._audio_buffer.extend(int16_data)
            while len(self._audio_buffer) >= self._send_stride:
                chunk = bytes(self._audio_buffer[:self._send_stride])
                self._audio_buffer = self._audio_buffer[self._send_stride:]
                asyncio.run_coroutine_threadsafe(ws.send(chunk), loop)

        # Read current state
        with self._lock:
            if self._has_endpoint:
                text = self._committed_text
                self._has_endpoint = False
                self._committed_text = ""
                return text, True
            return self._partial_text, False

    def reset(self) -> None:
        """Reset internal transcript state and signal end-of-utterance."""
        with self._lock:
            self._partial_text = ""
            self._committed_text = ""
            self._has_endpoint = False

        ws = self._ws
        loop = self._loop
        if ws is not None and loop is not None:
            # Flush remaining audio
            remaining = bytes(self._audio_buffer)
            self._audio_buffer = bytearray()
            if remaining:
                asyncio.run_coroutine_threadsafe(ws.send(remaining), loop)

            # Signal end-of-utterance (protocol-dependent)
            if self._is_dashscope:
                finish_msg = json.dumps({
                    "header": {
                        "action": "finish-task",
                        "task_id": self._task_id,
                        "streaming": "duplex",
                    },
                    "payload": {"input": {}},
                })
            else:
                finish_msg = json.dumps({"is_speaking": False})

            asyncio.run_coroutine_threadsafe(ws.send(finish_msg), loop)

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
