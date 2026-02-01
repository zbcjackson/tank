"""ASR (Automatic Speech Recognition) using faster-whisper."""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger("ASR")

# Common Whisper hallucination phrases to strip from transcript start/end (case-insensitive)
_HALLUCINATION_PHRASES = (
    "thank you",
    "thanks for watching",
    "thanks for listening",
)
_HALLUCINATION_LEAD_PATTERNS = tuple(
    re.compile(r"^\s*[.,!?]*\s*" + re.escape(p) + r"[.,!?\s]*", re.IGNORECASE)
    for p in _HALLUCINATION_PHRASES
)
_HALLUCINATION_TRAIL_PATTERNS = tuple(
    re.compile(r"[.,!?\s]*" + re.escape(p) + r"\s*[.,!?]*\s*$", re.IGNORECASE)
    for p in _HALLUCINATION_PHRASES
)
# Reduce noise from faster-whisper
logging.getLogger("faster_whisper").setLevel(logging.WARNING)


def _strip_hallucination_phrases(text: str) -> str:
    """
    Remove common Whisper hallucination phrases from start and end of text.
    Case-insensitive; allows optional punctuation/whitespace around phrases.
    """
    t = text.strip()
    while True:
        changed = False
        for lead_re, trail_re in zip(_HALLUCINATION_LEAD_PATTERNS, _HALLUCINATION_TRAIL_PATTERNS):
            t_new = lead_re.sub("", t).strip()
            t_new = trail_re.sub("", t_new).strip()
            if t_new != t:
                t = t_new
                changed = True
                break
        if not changed:
            break
    return t


class ASR:
    """
    Automatic Speech Recognition using faster-whisper.

    Multi-language with auto-detect. Model is loaded once and cached by Hugging Face.
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "default",
    ):
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

        started_at = time.time()
        logger.info("ASR started at %.3f", started_at)

        segments, info = self._model.transcribe(
            pcm,
            language=None,
            vad_filter=False,
            log_progress=False,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        text = _strip_hallucination_phrases(text)
        language = getattr(info, "language", None)
        confidence = getattr(info, "language_probability", None)

        ended_at = time.time()
        duration_s = ended_at - started_at
        logger.info("ASR ended at %.3f, duration_s=%.3f", ended_at, duration_s)
        return (text, language, confidence)
