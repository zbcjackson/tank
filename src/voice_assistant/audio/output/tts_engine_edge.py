"""Edge TTS backend: only file that imports edge_tts."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import AsyncIterator, Callable, Optional

import edge_tts
from pydub import AudioSegment

from ...config.settings import VoiceAssistantConfig
from .types import AudioChunk
from .tts import TTSEngine

logger = logging.getLogger(__name__)


class EdgeTTSEngine(TTSEngine):
    """TTS engine using Microsoft Edge TTS. Decodes MP3 stream to PCM."""

    def __init__(self, config: VoiceAssistantConfig):
        self._config = config

    def _voice_for_language(self, language: str) -> str:
        if language.startswith("zh") or language == "chinese":
            return self._config.tts_voice_zh
        return self._config.tts_voice_en

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: Optional[str] = None,
        is_interrupted: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[AudioChunk]:
        voice = voice or self._voice_for_language(language)
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if is_interrupted and is_interrupted():
                break
            if chunk.get("type") != "audio":
                continue
            data = chunk.get("data")
            if not data:
                continue
            try:
                seg = AudioSegment.from_file(BytesIO(data), format="mp3")
            except Exception as e:
                logger.warning("Failed to decode MP3 chunk: %s", e)
                continue
            yield AudioChunk(
                data=seg.raw_data,
                sample_rate=seg.frame_rate,
                channels=seg.channels,
            )
