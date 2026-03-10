"""ElevenLabs realtime streaming TTS engine.

Uses the ElevenLabs WebSocket ``stream-input`` API for lowest-latency TTS.
Text is sent incrementally and audio is received as base64-encoded PCM chunks.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator, Callable

import websockets

from tank_contracts.tts import AudioChunk, TTSEngine

logger = logging.getLogger("ElevenLabsTTS")

WS_URL_TEMPLATE = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
DEFAULT_MODEL = "eleven_flash_v2_5"
DEFAULT_SAMPLE_RATE = 24000
CHANNELS = 1


class ElevenLabsTTSEngine(TTSEngine):
    """TTS engine using ElevenLabs WebSocket stream-input API.

    Opens a new WebSocket per ``generate_stream`` call, sends the full text
    in one shot (with flush), and yields PCM audio chunks as they arrive.
    """

    def __init__(self, config: dict) -> None:
        self._api_key: str = config["api_key"]
        self._voice_id: str = config["voice_id"]
        self._voice_id_zh: str = config.get("voice_id_zh", self._voice_id)
        self._model_id: str = config.get("model_id", DEFAULT_MODEL)
        self._sample_rate: int = int(config.get("sample_rate", DEFAULT_SAMPLE_RATE))
        self._stability: float = float(config.get("stability", 0.5))
        self._similarity_boost: float = float(config.get("similarity_boost", 0.75))

    def _voice_for_language(self, language: str) -> str:
        if language.startswith("zh") or language == "chinese":
            return self._voice_id_zh
        return self._voice_id

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """Stream PCM audio from ElevenLabs for the given text."""
        voice_id = voice or self._voice_for_language(language)
        url = WS_URL_TEMPLATE.format(voice_id=voice_id)
        url += f"?model_id={self._model_id}"
        url += f"&output_format=pcm_{self._sample_rate}"

        async with websockets.connect(url) as ws:
            # 1. Send initialisation message (includes API key + voice settings)
            init_msg = json.dumps({
                "text": " ",
                "voice_settings": {
                    "stability": self._stability,
                    "similarity_boost": self._similarity_boost,
                },
                "xi-api-key": self._api_key,
            })
            await ws.send(init_msg)

            # 2. Send the full text + flush to trigger generation
            text_msg = json.dumps({
                "text": text,
                "flush": True,
            })
            await ws.send(text_msg)

            # 3. Send empty string to signal end of input
            await ws.send(json.dumps({"text": ""}))

            # 4. Receive audio chunks until isFinal or connection closes
            async for raw in ws:
                if is_interrupted and is_interrupted():
                    logger.debug("ElevenLabs TTS: interrupted, closing")
                    break

                msg = json.loads(raw)
                audio_b64 = msg.get("audio")
                is_final = msg.get("isFinal", False)

                if audio_b64:
                    pcm_bytes = base64.b64decode(audio_b64)
                    if pcm_bytes:
                        yield AudioChunk(
                            data=pcm_bytes,
                            sample_rate=self._sample_rate,
                            channels=CHANNELS,
                        )

                if is_final:
                    break
