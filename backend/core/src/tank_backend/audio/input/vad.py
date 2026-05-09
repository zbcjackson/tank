"""Silero VAD-based voice activity detection.

Two-tier split:

* ``VADEngine`` — process-global, loads the Silero ONNX model once, exposes
  ``create_stream()``.
* ``VADStream`` — per-session state (VADIterator, pre-roll buffer, chunk
  buffer, threshold); cheap to construct.

``SileroVAD`` is kept as a deprecated alias for ``VADStream`` — callers that
constructed ``SileroVAD(cfg, sample_rate)`` directly still work for one
release, but each such call now loads its own model and defeats the
singleton. New code should construct via ``VADEngine().create_stream(cfg)``.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np
from silero_vad import VADIterator, load_silero_vad

from .types import SegmenterConfig

logger = logging.getLogger("VAD")


class VADStatus(Enum):
    """Voice activity detection status."""

    NO_SPEECH = auto()     # No speech detected, no utterance
    START_SPEECH = auto()  # Speech just started (first frame of utterance)
    IN_SPEECH = auto()     # Speech continuing, accumulating frames
    END_SPEECH = auto()    # Speech ended, utterance finalized


@dataclass(frozen=True)
class VADResult:
    """Result from VAD processing."""

    status: VADStatus
    utterance_pcm: np.ndarray | None = None
    sample_rate: int | None = None
    started_at_s: float | None = None
    ended_at_s: float | None = None


class VADEngine:
    """Process-global Silero VAD engine. Owns the ONNX model.

    Load once at startup, then call ``create_stream()`` per session.
    The model is threadsafe-by-copy: each stream gets its own ``VADIterator``
    but they share the underlying Silero weights.
    """

    def __init__(self) -> None:
        self._model = load_silero_vad(onnx=True, opset_version=16)
        logger.info("VADEngine initialized (Silero ONNX model loaded)")

    def create_stream(
        self,
        cfg: SegmenterConfig | None = None,
        sample_rate: int = 16000,
    ) -> VADStream:
        """Create a fresh per-session VAD stream.

        Each stream owns its own VADIterator (which wraps the shared model)
        plus state buffers. Streams are cheap to create.
        """
        return VADStream(engine=self, cfg=cfg or SegmenterConfig(), sample_rate=sample_rate)

    def close(self) -> None:
        """Release engine resources. No-op today — Silero model has no
        explicit lifecycle."""


class VADStream:
    """
    Per-session Silero VAD stream.

    Holds per-session state: the VADIterator (wrapping the shared model),
    pre-roll buffer, chunk buffer, speech timing, and threshold.
    """

    def __init__(
        self,
        engine: VADEngine | None = None,
        cfg: SegmenterConfig | None = None,
        sample_rate: int = 16000,
    ):
        """
        Initialize a VADStream.

        Args:
            engine: Shared VADEngine that owns the Silero model. If None,
                a private engine is loaded (legacy path — prefer passing
                an engine from AppContext).
            cfg: Segmenter configuration
            sample_rate: Audio sample rate (default: 16000 Hz)
        """
        if cfg is None:
            cfg = SegmenterConfig()

        self._speech_process_started_at_s = None
        self._speech_process_ended_at_s = None
        self._cfg = cfg
        self._sample_rate = sample_rate

        # State tracking
        self._in_speech = False
        self._speech_pcm_parts: list[np.ndarray] = []
        self._speech_started_at_s: float | None = None
        self._last_voice_at_s: float | None = None  # For silence timeout tracking

        # Chunk buffering (for 512-sample chunks required by silero-vad)
        self._chunk_buffer = np.array([], dtype=np.float32)
        self._chunk_size = 512  # Required chunk size for 16kHz
        self._last_chunk_has_voice = False  # Track last processed chunk's voice state

        # Pre-roll buffer (ring buffer for audio before speech start)
        frame_ms = 20  # Standard frame size
        pre_roll_frames = int(cfg.pre_roll_ms / frame_ms)
        self._pre_roll_buffer: deque[np.ndarray] = deque(maxlen=pre_roll_frames)

        # Resolve engine — load a private one if not provided (legacy path)
        self._engine = engine or VADEngine()
        self._default_threshold = cfg.speech_threshold
        self._vad_iterator = VADIterator(
            self._engine._model,
            threshold=cfg.speech_threshold,
            sampling_rate=self._sample_rate,
        )

    def set_threshold(self, value: float) -> None:
        """Dynamically adjust the VAD speech threshold."""
        self._vad_iterator.threshold = value
        logger.info("VAD threshold changed to %.2f", value)

    def reset_threshold(self) -> None:
        """Restore the VAD speech threshold to its configured default."""
        self.set_threshold(self._default_threshold)

    def _process_chunk(self, chunk: np.ndarray) -> bool:
        """
        Process a 512-sample chunk and return speech detection result.
        """
        if len(chunk) < self._chunk_size:
            # Partial chunk, use energy threshold
            energy = np.sqrt(np.mean(chunk**2))
            return energy > 0.01

        # Full chunk, use model inference
        result = self._vad_iterator(chunk, return_seconds=False)
        return result is not None

    def _process_pending_chunks(self) -> bool | None:
        """Process any complete chunks in the buffer."""
        has_voice = None

        while len(self._chunk_buffer) >= self._chunk_size:
            chunk = self._chunk_buffer[: self._chunk_size]
            self._chunk_buffer = self._chunk_buffer[self._chunk_size :]

            chunk_has_voice = self._process_chunk(chunk)
            self._last_chunk_has_voice = chunk_has_voice

            has_voice = chunk_has_voice if has_voice is None else has_voice or chunk_has_voice

        return has_voice

    def _has_voice_activity(self, pcm: np.ndarray) -> bool:
        """
        Detect voice activity by buffering frames into chunks.
        """
        self._chunk_buffer = np.concatenate([self._chunk_buffer, pcm])

        chunk_result = self._process_pending_chunks()

        if chunk_result is not None:
            return chunk_result

        if len(self._chunk_buffer) > 0:
            energy = np.sqrt(np.mean(self._chunk_buffer**2))
            return energy > 0.01

        return self._last_chunk_has_voice

    def _finalize_utterance(self, ended_at_s: float) -> VADResult:
        """
        Build END_SPEECH result from current speech state and reset.
        """
        utterance_pcm = (
            np.concatenate(self._speech_pcm_parts)
            if self._speech_pcm_parts
            else np.array([], dtype=np.float32)
        )
        started_at = self._speech_started_at_s or ended_at_s
        self._in_speech = False
        self._speech_pcm_parts = []
        self._speech_started_at_s = None
        self._last_voice_at_s = None
        self._speech_process_ended_at_s = time.time()
        duration_s = self._speech_process_ended_at_s - (
            self._speech_process_started_at_s or self._speech_process_ended_at_s
        )
        logger.info(
            "VAD speech process ended at %.3f taking %.3f s, "
            "speech started_at_s=%.3f, ended_at_s=%.3f",
            self._speech_process_ended_at_s,
            duration_s,
            started_at,
            ended_at_s,
        )
        return VADResult(
            status=VADStatus.END_SPEECH,
            utterance_pcm=utterance_pcm,
            sample_rate=self._sample_rate,
            started_at_s=started_at,
            ended_at_s=ended_at_s,
        )

    def process_frame(
        self,
        pcm: np.ndarray,
        timestamp_s: float,
    ) -> VADResult:
        """
        Process a single audio frame.
        """
        # Always update pre-roll buffer
        self._pre_roll_buffer.append(pcm.copy())

        # Check silence timeout BEFORE processing voice activity
        if self._in_speech and self._last_voice_at_s is not None:
            silence_duration_ms = (timestamp_s - self._last_voice_at_s) * 1000.0
            if silence_duration_ms >= self._cfg.min_silence_ms:
                if self._speech_started_at_s is not None:
                    speech_duration_ms = (
                        self._last_voice_at_s - self._speech_started_at_s
                    ) * 1000.0
                    if speech_duration_ms < self._cfg.min_speech_ms:
                        self._in_speech = False
                        self._speech_pcm_parts = []
                        self._speech_started_at_s = None
                        self._last_voice_at_s = None
                        return VADResult(status=VADStatus.NO_SPEECH)

                return self._finalize_utterance(self._last_voice_at_s or timestamp_s)

        has_voice = self._has_voice_activity(pcm)

        if not self._in_speech:
            if not has_voice:
                return VADResult(status=VADStatus.NO_SPEECH)

            # Voice start detected - include pre-roll in utterance
            self._in_speech = True
            self._speech_started_at_s = timestamp_s
            self._last_voice_at_s = timestamp_s
            self._speech_process_started_at_s = time.time()
            logger.info(
                "VAD speech process started at %.3f, speech started at %.3f",
                self._speech_process_started_at_s,
                timestamp_s,
            )

            pre_roll_parts = list(self._pre_roll_buffer)
            self._speech_pcm_parts = pre_roll_parts + [pcm]
            return VADResult(
                status=VADStatus.START_SPEECH,
                started_at_s=timestamp_s,
            )

        # In speech state
        self._speech_pcm_parts.append(pcm)

        # Check max_utterance_ms
        if self._speech_started_at_s is not None:
            utterance_duration_ms = (timestamp_s - self._speech_started_at_s) * 1000.0
            if utterance_duration_ms >= self._cfg.max_utterance_ms:
                return self._finalize_utterance(timestamp_s)

        if has_voice:
            self._last_voice_at_s = timestamp_s

        return VADResult(status=VADStatus.IN_SPEECH)

    def flush(self, now_s: float) -> VADResult:
        """Force finalize any in-progress speech."""
        if not self._in_speech:
            return VADResult(status=VADStatus.NO_SPEECH)

        if len(self._chunk_buffer) > 0:
            self._process_chunk(self._chunk_buffer)
            self._chunk_buffer = np.array([], dtype=np.float32)

        if len(self._speech_pcm_parts) > 0:
            return self._finalize_utterance(now_s)
        self._in_speech = False
        self._speech_pcm_parts = []
        self._speech_started_at_s = None
        return VADResult(status=VADStatus.NO_SPEECH)


# Backward-compatible alias. Callers that used ``SileroVAD(cfg, sample_rate)``
# continue to work, but each such call loads its own Silero model. New code
# should construct via ``VADEngine().create_stream(cfg)``.
class SileroVAD(VADStream):
    """Deprecated alias for ``VADStream`` (loads a private ``VADEngine``)."""

    def __init__(
        self,
        cfg: SegmenterConfig | None = None,
        sample_rate: int = 16000,
    ) -> None:
        super().__init__(engine=None, cfg=cfg, sample_rate=sample_rate)


__all__ = [
    "SileroVAD",
    "VADEngine",
    "VADResult",
    "VADStatus",
    "VADStream",
]
