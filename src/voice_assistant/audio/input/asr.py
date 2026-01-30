"""ASR (Automatic Speech Recognition) using faster-whisper."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class ASR:
    """
    Automatic Speech Recognition using faster-whisper.

    Multi-language with auto-detect. Model is loaded once and cached by Hugging Face.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "default",
    ):
        from faster_whisper import WhisperModel

        logger.info("Loading ASR model: %s (device=%s)", model_size, device)
        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
        self._model_size = model_size

    def transcribe(
        self,
        pcm: np.ndarray,
        sample_rate: int,
    ) -> tuple[str, Optional[str], Optional[float]]:
        """
        Transcribe audio to text with language auto-detect.

        Args:
            pcm: Mono float32 audio (e.g. 16 kHz).
            sample_rate: Sample rate of pcm (expected 16000).

        Returns:
            (text, language, confidence). Empty pcm returns ("", None, None).
        """
        if pcm.size == 0:
            return ("", None, None)

        segments, info = self._model.transcribe(
            pcm,
            language=None,
            vad_filter=False,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        language = getattr(info, "language", None)
        confidence = getattr(info, "language_probability", None)
        return (text, language, confidence)
