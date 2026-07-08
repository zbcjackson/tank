"""Local offline Chatterbox in-process TTS engine.

Chatterbox (Resemble AI, MIT) is an expressive local TTS model with an
``exaggeration`` emotion control. Synthesis produces a full waveform per call;
this engine converts it to s16le PCM and yields fixed-size chunks. The heavy
``chatterbox-tts`` / ``torch`` deps are imported lazily so a default install
stays light. CPU synthesis works with no GPU but is slow.

All generated audio carries Chatterbox's Perth neural watermark.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable

import numpy as np
from tank_contracts.tts import AudioChunk, TTSEngine

logger = logging.getLogger("ChatterboxTTS")

DEFAULT_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_BYTES = 4096


def _load_chatterbox_cls():
    """Lazily import Chatterbox; raise a clear error if it isn't installed."""
    try:
        from chatterbox.tts import ChatterboxTTS  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - exercised via patched import
        raise RuntimeError(
            "Chatterbox is not installed. Install it to use tts-chatterbox:\n"
            "  uv pip install chatterbox-tts"
        ) from e
    return ChatterboxTTS


def _to_int16_pcm(waveform) -> bytes:
    """Convert a torch/numpy waveform in [-1, 1] to s16le PCM bytes."""
    # torch tensors expose .detach().cpu().numpy(); numpy arrays pass through.
    if hasattr(waveform, "detach"):
        waveform = waveform.detach().cpu().numpy()
    audio = np.asarray(waveform, dtype=np.float32).reshape(-1)
    return (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()


class ChatterboxTTSEngine(TTSEngine):
    """In-process TTS engine using the Chatterbox model (CPU or CUDA)."""

    def __init__(self, config: dict) -> None:
        self._device = config.get("device", "cpu")
        self._exaggeration = float(config.get("exaggeration", 0.5))
        self._cfg_weight = float(config.get("cfg_weight", 0.5))
        self._voice_prompt_path = config.get("voice_prompt_path")
        self._config_sample_rate = int(config.get("sample_rate", DEFAULT_SAMPLE_RATE))
        self._model = None  # lazy-loaded
        self._sample_rate = self._config_sample_rate

    def _get_model(self):
        if self._model is None:
            chatterbox_cls = _load_chatterbox_cls()
            if self._device == "cpu":
                logger.warning(
                    "Chatterbox running on CPU — synthesis will be slow "
                    "(several seconds per utterance)."
                )
            logger.info("Loading Chatterbox model (device=%s)", self._device)
            self._model = chatterbox_cls.from_pretrained(device=self._device)
            # Emit the model's native sample rate when available.
            self._sample_rate = int(getattr(self._model, "sr", self._sample_rate))
        return self._model

    def _synthesize(self, text: str):
        """Run blocking Chatterbox synthesis; return a waveform."""
        model = self._get_model()
        kwargs: dict = {
            "exaggeration": self._exaggeration,
            "cfg_weight": self._cfg_weight,
        }
        if self._voice_prompt_path:
            kwargs["audio_prompt_path"] = self._voice_prompt_path
        return model.generate(text, **kwargs)

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """Stream PCM audio synthesized locally by Chatterbox."""
        # CPU/GPU-bound synthesis off the event loop.
        waveform = await asyncio.to_thread(self._synthesize, text)

        if is_interrupted and is_interrupted():
            logger.debug("Chatterbox TTS: interrupted")
            return

        pcm = _to_int16_pcm(waveform)
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
