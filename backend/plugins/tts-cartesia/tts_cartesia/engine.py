"""Cartesia Sonic realtime streaming TTS engine.

Uses the Cartesia WebSocket ``/tts/websocket`` API for low-latency TTS. The
full transcript is sent in one message and audio is received as base64-encoded
raw PCM (s16le) chunks.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable

import websockets
from tank_contracts.tts import AudioChunk, TTSEngine, select_voice

logger = logging.getLogger("CartesiaTTS")

WS_URL = "wss://api.cartesia.ai/tts/websocket"
DEFAULT_MODEL = "sonic-3"
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_VERSION = "2026-03-01"
CHANNELS = 1


class CartesiaTTSEngine(TTSEngine):
    """TTS engine using the Cartesia Sonic WebSocket API.

    Opens a new WebSocket per ``generate_stream`` call, sends the full text,
    and yields PCM audio chunks as they arrive.
    """

    def __init__(self, config: dict) -> None:
        self._api_key: str = config["api_key"]
        self._model_id: str = config.get("model_id", DEFAULT_MODEL)
        self._sample_rate: int = int(config.get("sample_rate", DEFAULT_SAMPLE_RATE))
        self._version: str = config.get("cartesia_version", DEFAULT_VERSION)
        self._emotion = config.get("emotion")
        default_voice: str = config.get("default_voice", "")
        self._voices: dict[str, str] = {
            **(config.get("voices") or {}),
        }
        self._default_voice = default_voice or next(iter(self._voices.values()), "")

    def _voice_for_language(self, language: str) -> str:
        return select_voice(language, self._voices, self._default_voice)

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """Stream PCM audio from Cartesia for the given text."""
        voice_id = voice or self._voice_for_language(language)
        url = f"{WS_URL}?cartesia_version={self._version}"
        headers = {"X-API-Key": self._api_key}

        request: dict = {
            "model_id": self._model_id,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "context_id": uuid.uuid4().hex,
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": self._sample_rate,
            },
            "continue": False,
        }
        if language and language != "auto":
            request["language"] = language.split("-")[0]
        if self._emotion:
            request["generation_config"] = {"emotion": self._emotion}

        async with websockets.connect(url, additional_headers=headers) as ws:
            await ws.send(json.dumps(request))

            async for raw in ws:
                if is_interrupted and is_interrupted():
                    logger.debug("Cartesia TTS: interrupted, closing")
                    break

                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "chunk":
                    audio_b64 = msg.get("data")
                    if audio_b64:
                        pcm_bytes = base64.b64decode(audio_b64)
                        # Guard int16 alignment (raw s16le should always be even).
                        if len(pcm_bytes) % 2 == 1:
                            pcm_bytes = pcm_bytes[:-1]
                        if pcm_bytes:
                            yield AudioChunk(
                                data=pcm_bytes,
                                sample_rate=self._sample_rate,
                                channels=CHANNELS,
                            )
                elif msg_type == "error":
                    logger.warning(
                        "Cartesia TTS error: %s / %s",
                        msg.get("title"), msg.get("message"),
                    )
                    break
                elif msg_type == "done":
                    break
