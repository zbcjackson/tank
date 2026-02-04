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
    "for watching",
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
    
    Since this project uses custom VAD (SileroVAD), vad_filter is set to False
    and threshold parameters are disabled by default to avoid double-filtering.
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "default",
        # Hallucination prevention parameters
        log_prob_threshold: Optional[float] = None,
        no_speech_threshold: Optional[float] = None,
        compression_ratio_threshold: Optional[float] = None,
        hallucination_silence_threshold: Optional[float] = None,
        language_detection_threshold: float = 0.5,
        condition_on_previous_text: bool = False,
        vad_filter: bool = False,
    ):
        """
        Initialize ASR model.

        Args:
            model_size: Whisper model size (e.g., "large-v3").
            device: Device to use ("cpu", "cuda", etc.).
            compute_type: Computation type ("default", "float16", etc.).
            log_prob_threshold: If average log probability is below this value,
                treat segment as failed. None to disable. Default None (disabled
                since custom VAD is used).
            no_speech_threshold: If no_speech probability exceeds this AND log_prob
                is below threshold, consider segment silent. None to disable.
                Default None (disabled since custom VAD is used).
            compression_ratio_threshold: If compression ratio exceeds this value,
                treat as failed (repetitive). None to disable. Default None.
            hallucination_silence_threshold: When word_timestamps=True, skip silent
                periods longer than this (seconds) when hallucination detected.
                None to disable. Default None.
            language_detection_threshold: Language detection confidence threshold.
                Default 0.5.
            condition_on_previous_text: If True, use previous output as prompt.
                Setting False reduces repetition hallucinations. Default False.
            vad_filter: Use faster-whisper's built-in VAD. Default False (project
                uses custom SileroVAD).
        """
        logger.info("Loading ASR model: %s (device=%s)", model_size, device)
        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
        self._model_size = model_size
        self._log_prob_threshold = log_prob_threshold
        self._no_speech_threshold = no_speech_threshold
        self._compression_ratio_threshold = compression_ratio_threshold
        self._hallucination_silence_threshold = hallucination_silence_threshold
        self._language_detection_threshold = language_detection_threshold
        self._condition_on_previous_text = condition_on_previous_text
        self._vad_filter = vad_filter

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
            vad_filter=self._vad_filter,
            log_progress=False,
            log_prob_threshold=self._log_prob_threshold,
            no_speech_threshold=self._no_speech_threshold,
            compression_ratio_threshold=self._compression_ratio_threshold,
            hallucination_silence_threshold=self._hallucination_silence_threshold,
            language_detection_threshold=self._language_detection_threshold,
            condition_on_previous_text=self._condition_on_previous_text,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        text = _strip_hallucination_phrases(text)
        language = getattr(info, "language", None)
        confidence = getattr(info, "language_probability", None)

        ended_at = time.time()
        duration_s = ended_at - started_at
        logger.info("ASR ended at %.3f, duration_s=%.3f", ended_at, duration_s)
        return (text, language, confidence)
