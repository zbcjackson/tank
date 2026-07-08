"""Local offline Kokoro-82M in-process TTS engine.

Kokoro is a tiny (82M) open-weight TTS model that runs on CPU. Synthesis
produces a full float32 waveform per text segment; this engine converts it to
s16le PCM and yields fixed-size chunks. The heavy ``kokoro`` dependency is
imported lazily so a default install stays light.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable

import numpy as np
from tank_contracts.tts import AudioChunk, TTSEngine, select_voice

logger = logging.getLogger("KokoroTTS")

DEFAULT_SAMPLE_RATE = 24000  # Kokoro emits 24 kHz
CHANNELS = 1
CHUNK_BYTES = 4096

# ISO 639-1 → Kokoro lang_code.
_LANG_CODES = {
    "en": "a",  # American English
    "zh": "z",  # Mandarin (needs misaki[zh])
    "es": "e",
    "fr": "f",
    "hi": "h",
    "it": "i",
    "pt": "p",
    "ja": "j",  # needs misaki[ja]
}


def _load_kpipeline_cls():
    """Lazily import Kokoro; raise a clear error if it isn't installed."""
    try:
        from kokoro import KPipeline  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - exercised via patched import
        raise RuntimeError(
            "Kokoro is not installed. Install it to use tts-kokoro:\n"
            "  uv pip install kokoro soundfile\n"
            "and the espeak-ng system package (e.g. apt-get install espeak-ng)."
        ) from e
    return KPipeline


class KokoroTTSEngine(TTSEngine):
    """In-process TTS engine using the Kokoro-82M model on CPU."""

    def __init__(self, config: dict) -> None:
        self._sample_rate = int(config.get("sample_rate", DEFAULT_SAMPLE_RATE))
        self._speed = float(config.get("speed", 1.0))
        self._voices: dict[str, str] = {
            "en": "af_heart",
            **(config.get("voices") or {}),
        }
        self._default_voice = config.get("default_voice", "af_heart")
        # One KPipeline per lang_code, created on demand.
        self._pipelines: dict[str, object] = {}

    def _voice_for_language(self, language: str) -> str:
        return select_voice(language, self._voices, self._default_voice)

    def _lang_code(self, language: str) -> str:
        if not language or language == "auto":
            return "a"
        return _LANG_CODES.get(language.split("-")[0], "a")

    def _get_pipeline(self, lang_code: str):
        pipeline = self._pipelines.get(lang_code)
        if pipeline is None:
            kpipeline_cls = _load_kpipeline_cls()
            logger.info("Loading Kokoro pipeline (lang_code=%s)", lang_code)
            pipeline = kpipeline_cls(lang_code=lang_code)
            self._pipelines[lang_code] = pipeline
        return pipeline

    def _synthesize(self, pipeline, text: str, voice: str) -> list[np.ndarray]:
        """Run blocking Kokoro synthesis; return float32 audio segments."""
        segments: list[np.ndarray] = []
        for _gs, _ps, audio in pipeline(text, voice=voice, speed=self._speed):
            segments.append(np.asarray(audio, dtype=np.float32))
        return segments

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """Stream PCM audio synthesized locally by Kokoro."""
        voice_name = voice or self._voice_for_language(language)
        lang_code = self._lang_code(language)
        pipeline = self._get_pipeline(lang_code)

        # CPU-bound synthesis off the event loop.
        segments = await asyncio.to_thread(
            self._synthesize, pipeline, text, voice_name
        )

        for audio in segments:
            if is_interrupted and is_interrupted():
                logger.debug("Kokoro TTS: interrupted")
                return
            pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
            for i in range(0, len(pcm), CHUNK_BYTES):
                if is_interrupted and is_interrupted():
                    return
                chunk = pcm[i : i + CHUNK_BYTES]
                if len(chunk) % 2 == 1:  # keep int16 alignment
                    chunk = chunk[:-1]
                if chunk:
                    yield AudioChunk(
                        data=chunk,
                        sample_rate=self._sample_rate,
                        channels=CHANNELS,
                    )
