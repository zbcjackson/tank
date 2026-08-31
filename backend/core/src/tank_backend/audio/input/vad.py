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

from .smart_turn import SmartTurnAnalyzer, SmartTurnResult
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
    """Result from VAD processing.

    ``turn_id``/``turn_revision`` identify a speculative turn chain: the
    original commit carries revision 0; each reopen (resumed speech within
    ``speculative_reopen_ms``) increments the revision while keeping the
    same ``turn_id``.
    """

    status: VADStatus
    utterance_pcm: np.ndarray | None = None
    sample_rate: int | None = None
    started_at_s: float | None = None
    ended_at_s: float | None = None
    turn_id: str | None = None
    turn_revision: int = 0


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
        smart_turn: SmartTurnAnalyzer | None = None,
    ) -> VADStream:
        """Create a fresh per-session VAD stream.

        Each stream owns its own VADIterator (which wraps the shared model)
        plus state buffers. Streams are cheap to create.
        """
        return VADStream(
            engine=self,
            cfg=cfg or SegmenterConfig(),
            sample_rate=sample_rate,
            smart_turn=smart_turn,
        )

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
        smart_turn: SmartTurnAnalyzer | None = None,
    ):
        """
        Initialize a VADStream.

        Args:
            engine: Shared VADEngine that owns the Silero model. If None,
                a private engine is loaded (legacy path — prefer passing
                an engine from AppContext).
            cfg: Segmenter configuration
            sample_rate: Audio sample rate (default: 16000 Hz)
            smart_turn: Optional Smart Turn analyzer adjudicating each
                speech→silence boundary. When present, the Silero boundary
                fires at the analyzer's ``candidate_min_silence_ms`` as a
                *candidate* — the analyzer either commits the utterance or
                holds it open for continued speech. When None, the
                configured ``min_silence_ms`` is the endpoint (the
                pre-Smart-Turn behaviour).
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

        # Speculative turn identity: the chain currently being recorded.
        self._active_turn_id: str | None = None
        self._active_turn_revision: int = 0
        # The last commit is kept briefly so resumed speech within
        # ``speculative_reopen_ms`` reopens the same turn (revision + 1)
        # instead of starting a second user turn. Cleared lazily: the next
        # voice start either consumes it or finds it expired.
        self._reopen_turn_id: str | None = None
        self._reopen_revision: int = 0
        self._reopen_pcm: np.ndarray | None = None
        self._reopen_started_at_s: float | None = None
        self._reopen_last_voice_at_s: float | None = None

        # Endpoint policy: Smart Turn adjudication, or the plain silence
        # timeout when no analyzer is attached.
        self._smart_turn = smart_turn
        self._endpoint_silence_ms = (
            smart_turn.candidate_min_silence_ms if smart_turn else cfg.min_silence_ms
        )
        # Smart Turn "incomplete" hold: the utterance stays open until this
        # deadline, so a pause-and-continue merges into one utterance.
        self._st_pending = False
        self._st_hold_until_s: float | None = None

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

        if smart_turn is not None:
            logger.info(
                "VAD endpoint policy: Smart Turn adjudication "
                "(candidate silence %dms, incomplete hold %dms)",
                self._endpoint_silence_ms,
                smart_turn.incomplete_delay_ms,
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

        # Voice evidence in the leftover samples (< 512) after full-chunk
        # processing. During sustained speech the transition-based iterator
        # reports no result for full chunks (it only fires on start/end),
        # so a frame of big chunks + voiced leftover must OR the leftover
        # energy in — otherwise mid-speech frames read as silent, freezing
        # ``_last_voice_at_s`` and triggering premature silence boundaries.
        leftover_voice: bool | None = None
        if self._chunk_buffer.size > 0:
            energy = np.sqrt(np.mean(self._chunk_buffer**2))
            leftover_voice = bool(energy > 0.01)

        if chunk_result is None:
            if leftover_voice is not None:
                return leftover_voice
            return self._last_chunk_has_voice
        if leftover_voice is not None:
            return leftover_voice or chunk_result
        return chunk_result

    def _reset_speech_state(self) -> None:
        """Clear all in-speech state, including a pending Smart Turn hold.

        Every reset path must go through here (finalize, min-speech discard,
        flush) so a held utterance can never survive into the next turn.
        """
        self._in_speech = False
        self._speech_pcm_parts = []
        self._speech_started_at_s = None
        self._last_voice_at_s = None
        self._st_pending = False
        self._st_hold_until_s = None
        self._active_turn_id = None
        self._active_turn_revision = 0

    def _clear_reopen_state(self) -> None:
        """Drop the reopen candidate (consumed or expired)."""
        self._reopen_turn_id = None
        self._reopen_revision = 0
        self._reopen_pcm = None
        self._reopen_started_at_s = None
        self._reopen_last_voice_at_s = None

    def _adjudicate_endpoint(self) -> SmartTurnResult | None:
        """Run Smart Turn on the pending utterance; None = commit now.

        Returns None when no analyzer is attached (plain silence policy) or
        on any analyzer failure — failing open to an immediate commit, never
        hanging the turn on classifier trouble.
        """
        if self._smart_turn is None:
            return None
        utterance = np.concatenate(self._speech_pcm_parts)
        try:
            result = self._smart_turn.predict(utterance, sample_rate=self._sample_rate)
        except Exception:
            logger.warning(
                "Smart Turn inference failed — committing endpoint", exc_info=True,
            )
            return None
        logger.info(
            "Smart Turn verdict p=%.3f complete=%s (%.0fms inference)",
            result.probability,
            result.complete,
            result.inference_ms,
        )
        return result

    def _finalize_utterance(self, ended_at_s: float, *, arm_reopen: bool = True) -> VADResult:
        """
        Build END_SPEECH result from current speech state and reset.

        Silence/max-utterance endpoints arm the speculative reopen window
        (``arm_reopen=True``) so resumed speech can merge into the same
        turn. Explicit ends (``flush()`` — push-to-talk, interrupts) pass
        ``arm_reopen=False``: the caller signalled a hard turn boundary.
        """
        utterance_pcm = (
            np.concatenate(self._speech_pcm_parts)
            if self._speech_pcm_parts
            else np.array([], dtype=np.float32)
        )
        started_at = self._speech_started_at_s or ended_at_s
        turn_id = self._active_turn_id or f"turn_{started_at:.3f}"
        turn_revision = self._active_turn_revision
        last_voice_at_s = self._last_voice_at_s
        self._reset_speech_state()
        if arm_reopen and utterance_pcm.size > 0:
            self._reopen_turn_id = turn_id
            self._reopen_revision = turn_revision
            self._reopen_pcm = utterance_pcm
            self._reopen_started_at_s = started_at
            self._reopen_last_voice_at_s = last_voice_at_s
        else:
            self._clear_reopen_state()
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
            turn_id=turn_id,
            turn_revision=turn_revision,
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
            if self._st_pending:
                # Smart Turn said "incomplete": hold the utterance open for
                # continued speech; if the hold expires in silence, commit
                # anyway (fail-forward — the model may have been wrong).
                if self._st_hold_until_s is not None and timestamp_s >= self._st_hold_until_s:
                    return self._finalize_utterance(self._last_voice_at_s)
            else:
                silence_duration_ms = (timestamp_s - self._last_voice_at_s) * 1000.0
                if silence_duration_ms >= self._endpoint_silence_ms:
                    if self._speech_started_at_s is not None:
                        speech_duration_ms = (
                            self._last_voice_at_s - self._speech_started_at_s
                        ) * 1000.0
                        if speech_duration_ms < self._cfg.min_speech_ms:
                            self._reset_speech_state()
                            return VADResult(status=VADStatus.NO_SPEECH)

                    analyzer = self._smart_turn
                    verdict = self._adjudicate_endpoint()
                    if analyzer is None or verdict is None or verdict.complete:
                        return self._finalize_utterance(
                            self._last_voice_at_s or timestamp_s
                        )
                    # Incomplete: hold open for continued speech. Resumed
                    # voice clears the hold below; the next boundary
                    # re-adjudicates the (longer) utterance.
                    self._st_pending = True
                    self._st_hold_until_s = (
                        timestamp_s + analyzer.incomplete_delay_ms / 1000.0
                    )

        has_voice = self._has_voice_activity(pcm)

        if not self._in_speech:
            if not has_voice:
                return VADResult(status=VADStatus.NO_SPEECH)

            # Voice start detected. If the previous commit is still inside
            # the speculative reopen window, this speech continues that
            # turn: splice the committed audio back in front and bump the
            # revision, so pause-and-continue stays a single user turn.
            prefix_pcm = self._reopen_pcm
            pre_roll_parts = list(self._pre_roll_buffer)
            self._in_speech = True
            self._last_voice_at_s = timestamp_s
            self._speech_process_started_at_s = time.time()
            if (
                prefix_pcm is not None
                and self._reopen_turn_id is not None
                and self._reopen_last_voice_at_s is not None
                and (timestamp_s - self._reopen_last_voice_at_s) * 1000.0
                <= self._cfg.speculative_reopen_ms
            ):
                self._active_turn_id = self._reopen_turn_id
                self._active_turn_revision = self._reopen_revision + 1
                # Duration caps and the reported start stay anchored to the
                # original utterance — the merged turn *is* that turn.
                self._speech_started_at_s = self._reopen_started_at_s
                self._speech_pcm_parts = [prefix_pcm, *pre_roll_parts, pcm]
                self._clear_reopen_state()
                logger.info(
                    "VAD turn reopened: turn=%s revision=%d",
                    self._active_turn_id,
                    self._active_turn_revision,
                )
            else:
                self._clear_reopen_state()
                self._active_turn_id = None
                self._active_turn_revision = 0
                self._speech_started_at_s = timestamp_s
                self._speech_pcm_parts = pre_roll_parts + [pcm]
            logger.info(
                "VAD speech process started at %.3f, speech started at %.3f",
                self._speech_process_started_at_s,
                timestamp_s,
            )
            return VADResult(
                status=VADStatus.START_SPEECH,
                started_at_s=timestamp_s,
                turn_id=self._active_turn_id,
                turn_revision=self._active_turn_revision,
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
            if self._st_pending:
                # Speech resumed during the Smart Turn hold — the same
                # utterance continues; the next boundary re-adjudicates it.
                self._st_pending = False
                self._st_hold_until_s = None

        return VADResult(status=VADStatus.IN_SPEECH)

    def flush(self, now_s: float) -> VADResult:
        """Force finalize any in-progress speech.

        An explicit end (push-to-talk, interrupt flush) — the reopen window
        is not armed, the caller has declared the turn over.
        """
        if not self._in_speech:
            return VADResult(status=VADStatus.NO_SPEECH)

        if len(self._chunk_buffer) > 0:
            self._process_chunk(self._chunk_buffer)
            self._chunk_buffer = np.array([], dtype=np.float32)

        if len(self._speech_pcm_parts) > 0:
            return self._finalize_utterance(now_s, arm_reopen=False)
        self._reset_speech_state()
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
