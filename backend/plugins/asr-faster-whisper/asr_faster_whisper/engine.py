"""Local offline Faster-Whisper batch ASR engine.

Faster-Whisper is a CTranslate2 reimplementation of OpenAI Whisper. It is NOT a
streaming engine — it transcribes a complete utterance in one pass. This stream
therefore sets ``supports_streaming = False``: the pipeline buffers the full
utterance and hands it to ``process_pcm`` in a single call after VAD END_SPEECH,
and ``stop()`` returns the transcript.

The model is loaded once at the engine level and shared across streams.
"""

from __future__ import annotations

import logging

import numpy as np
from faster_whisper import WhisperModel
from tank_contracts import ASREngine, ASRStream

logger = logging.getLogger("FasterWhisperASR")


class FasterWhisperASRStream(ASRStream):
    """Per-utterance batch recognition session.

    Buffers PCM chunks and transcribes the concatenated audio on ``stop()``.
    """

    def __init__(self, engine: FasterWhisperASREngine) -> None:
        self._engine = engine
        self._chunks: list[np.ndarray] = []
        self._detected_language: str | None = None

    @property
    def supports_streaming(self) -> bool:
        # Batch-only: no meaningful partial transcripts.
        return False

    @property
    def detected_language(self) -> str | None:
        return self._detected_language

    def start(self) -> None:
        self._chunks = []
        self._detected_language = None

    def process_pcm(self, pcm: np.ndarray) -> str:
        # Accumulate; batch engines produce no partial transcript.
        self._chunks.append(np.asarray(pcm, dtype=np.float32))
        return ""

    def stop(self) -> str:
        if not self._chunks:
            return ""

        audio = np.concatenate(self._chunks)
        self._chunks = []

        text, language = self._engine.transcribe(audio)
        self._detected_language = language
        return text

    def close(self) -> None:
        self._chunks = []


class FasterWhisperASREngine(ASREngine):
    """Local offline ASR using Faster-Whisper (CTranslate2).

    Loads the Whisper model once and shares it across per-utterance streams.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "",
        beam_size: int = 5,
        sample_rate: int = 16000,
    ) -> None:
        self._language = language or None
        self._beam_size = beam_size
        self._sample_rate = sample_rate

        logger.info(
            "Loading Faster-Whisper model: size=%s device=%s compute_type=%s",
            model_size, device, compute_type,
        )
        self._model = WhisperModel(
            model_size, device=device, compute_type=compute_type
        )
        logger.info("Faster-Whisper model loaded")

    # ------------------------------------------------------------------
    # ASREngine contract
    # ------------------------------------------------------------------

    def create_stream(self) -> ASRStream:
        return FasterWhisperASRStream(self)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def close(self) -> None:
        logger.info("Faster-Whisper: Engine closed")

    # ------------------------------------------------------------------
    # Transcription (called by the per-stream wrapper)
    # ------------------------------------------------------------------

    def transcribe(self, audio: np.ndarray) -> tuple[str, str | None]:
        """Transcribe a complete float32 mono utterance.

        Returns:
            (transcript, detected_language) — language is an ISO 639-1 code
            reported by Whisper's acoustic language ID, or None.
        """
        segments, info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=self._beam_size,
        )
        text = "".join(segment.text for segment in segments).strip()
        language = getattr(info, "language", None)
        logger.debug(
            "Faster-Whisper: transcribed (lang=%s): %s",
            language, text[:50] if text else "(empty)",
        )
        return text, language
