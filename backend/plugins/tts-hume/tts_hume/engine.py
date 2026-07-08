"""Hume Octave emotionally-expressive streaming TTS engine.

Uses the Hume Octave streaming-input WebSocket API (``/v0/tts/stream/input``).
Octave adapts pitch, tempo, and emphasis to the emotional intent of the text
automatically; an optional ``description`` prompt shapes the persona/emotion.
Audio arrives as base64-encoded PCM snippets.

Note: Hume's streaming frame schema and PCM sample rate are validated
empirically — message parsing is deliberately tolerant (``.get`` guards).
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator, Callable

import websockets
from tank_contracts.tts import AudioChunk, TTSEngine, select_voice

logger = logging.getLogger("HumeTTS")

WS_URL = "wss://api.hume.ai/v0/tts/stream/input"
DEFAULT_SAMPLE_RATE = 24000
CHANNELS = 1


class HumeTTSEngine(TTSEngine):
    """TTS engine using the Hume Octave streaming-input WebSocket API.

    Opens a new WebSocket per ``generate_stream`` call, sends one utterance,
    and yields PCM audio chunks as snippets arrive.
    """

    def __init__(self, config: dict) -> None:
        self._api_key: str = config["api_key"]
        self._sample_rate: int = int(config.get("sample_rate", DEFAULT_SAMPLE_RATE))
        self._description: str | None = config.get("description")
        self._voice_id: str | None = config.get("voice_id")
        self._voice_name: str | None = config.get("voice_name")
        self._voices: dict[str, str] = {**(config.get("voices") or {})}
        self._default_voice = config.get("default_voice") or self._voice_name or ""

    def _voice_for_language(self, language: str) -> str | None:
        selected = select_voice(language, self._voices, self._default_voice)
        return selected or None

    def _build_voice(self, voice: str | None, language: str) -> dict | None:
        if voice:
            return {"name": voice}
        if self._voice_id:
            return {"id": self._voice_id}
        name = self._voice_for_language(language)
        if name:
            return {"name": name}
        return None

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """Stream PCM audio from Hume Octave for the given text."""
        headers = {"X-Hume-Api-Key": self._api_key}

        utterance: dict = {"text": text}
        if self._description:
            utterance["description"] = self._description
        voice_ref = self._build_voice(voice, language)
        if voice_ref:
            utterance["voice"] = voice_ref

        request = {
            "utterances": [utterance],
            "format": {"type": "pcm"},
            "instant_mode": True if voice_ref else False,
        }

        async with websockets.connect(WS_URL, additional_headers=headers) as ws:
            await ws.send(json.dumps(request))

            async for raw in ws:
                if is_interrupted and is_interrupted():
                    logger.debug("Hume TTS: interrupted, closing")
                    break

                msg = json.loads(raw)

                # Error envelope
                if msg.get("error") or msg.get("type") == "error":
                    logger.warning("Hume TTS error: %s", msg.get("message") or msg)
                    break

                audio_b64 = msg.get("audio")
                if audio_b64:
                    pcm_bytes = base64.b64decode(audio_b64)
                    if len(pcm_bytes) % 2 == 1:
                        pcm_bytes = pcm_bytes[:-1]
                    if pcm_bytes:
                        yield AudioChunk(
                            data=pcm_bytes,
                            sample_rate=self._sample_rate,
                            channels=CHANNELS,
                        )

                # Terminal snippet markers (tolerant to schema variants)
                if msg.get("is_last") or msg.get("isLast") or msg.get("type") == "done":
                    break
