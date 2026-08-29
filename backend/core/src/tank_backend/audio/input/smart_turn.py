"""Smart Turn v3.2 end-of-turn adjudication.

A conventional VAD decides *when speech stops*; Smart Turn decides *whether
the speaker is done*. It is an ONNX audio classifier (pipecat-ai
``smart-turn-v3``, Whisper-encoder derived) run once per Silero
speech→silence boundary — never per audio chunk — so its cost does not
scale with the audio stream.

``VADStream`` uses the analyzer's knobs as the endpoint policy when one is
attached: the Silero boundary fires at ``candidate_min_silence_ms`` (fast
candidate), the analyzer then either commits the utterance (``complete``)
or holds it open for ``incomplete_delay_ms`` of continued speech. Without
an analyzer (disabled / model missing / load failure) the stream falls back
to ``SegmenterConfig.min_silence_ms`` — the pre-Smart-Turn behaviour.

The timing knobs live on the analyzer (not in :mod:`tank_backend.config`)
so the audio layer takes a single ``smart_turn`` object and the fallback
path needs no config at all.

Model is expected at ``DEFAULT_MODEL_PATH`` (CWD-relative, like the other
model paths in ``config.yaml``); fetch it with
``uv run python scripts/download_models.py smart-turn``.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ...config.models import SmartTurnConfig

logger = logging.getLogger(__name__)

MODEL_REPO_ID = "pipecat-ai/smart-turn-v3"
MODEL_VERSION = "v3.2"
MODEL_FILENAME = f"smart-turn-{MODEL_VERSION}-cpu.onnx"
MODEL_SAMPLE_RATE = 16000
MAX_AUDIO_SECONDS = 8
MAX_AUDIO_SAMPLES = MAX_AUDIO_SECONDS * MODEL_SAMPLE_RATE
# Below this (100 ms of audio) the classifier is useless — treat any such
# blip as a complete (i.e. harmless) utterance without paying for inference.
MIN_AUDIO_SAMPLES = 1600
EXPECTED_FEATURE_SHAPE = (1, 80, 800)
# CWD-relative, consistent with the other model paths in config.yaml
# (the server runs from ``backend/core``, so this resolves into
# ``backend/models/``).
DEFAULT_MODEL_PATH = f"../models/smart-turn/{MODEL_FILENAME}"


@dataclass(frozen=True)
class SmartTurnResult:
    """Result of one Smart Turn prediction."""

    complete: bool
    probability: float
    inference_ms: float


class SmartTurnAnalyzer:
    """Run the Smart Turn v3.2 ONNX model on up to eight seconds of audio."""

    def __init__(
        self,
        *,
        model_path: str | None = None,
        threshold: float = 0.5,
        cpu_count: int = 1,
        candidate_min_silence_ms: int = 250,
        incomplete_delay_ms: int = 600,
        warmup: bool = True,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"Smart Turn threshold must be between 0 and 1, got {threshold}"
            )
        if cpu_count < 1:
            raise ValueError(f"Smart Turn cpu_count must be at least 1, got {cpu_count}")

        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ImportError(
                "Smart Turn requires the `onnxruntime` package for CPU inference."
            ) from exc

        from transformers import WhisperFeatureExtractor

        self.threshold = threshold
        # Endpoint policy carried for VADStream (see module docstring).
        self.candidate_min_silence_ms = candidate_min_silence_ms
        self.incomplete_delay_ms = incomplete_delay_ms
        self._lock = threading.Lock()

        self.model_path = Path(model_path or DEFAULT_MODEL_PATH).expanduser()
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Smart Turn model not found: {self.model_path}")

        session_options = ort.SessionOptions()
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        session_options.inter_op_num_threads = 1
        session_options.intra_op_num_threads = cpu_count
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(self.model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self.session.get_inputs()[0].name
        self._feature_extractor = WhisperFeatureExtractor(chunk_length=MAX_AUDIO_SECONDS)

        logger.info(
            "Loaded Smart Turn %s from %s (threshold=%.2f, candidate silence %dms, "
            "incomplete delay %dms)",
            MODEL_VERSION,
            self.model_path,
            threshold,
            candidate_min_silence_ms,
            incomplete_delay_ms,
        )
        if warmup:
            self.predict(np.zeros(MODEL_SAMPLE_RATE, dtype=np.float32))

    @classmethod
    def from_config(cls, cfg: SmartTurnConfig) -> SmartTurnAnalyzer | None:
        """Build an analyzer from the ``smart_turn:`` config section.

        Never raises: returns ``None`` (and the caller's VAD falls back to
        the plain silence policy) when the feature is disabled, the model
        file is absent, or loading fails. A missing model at the default
        path is the expected state on a fresh install and logs at INFO.
        """
        if not cfg.enabled:
            return None

        resolved = Path(cfg.model_path or DEFAULT_MODEL_PATH).expanduser()
        if not resolved.is_file():
            logger.info(
                "Smart Turn model not found at %s — endpointing falls back to the "
                "plain silence policy (%d ms). Fetch the model with "
                "`uv run python scripts/download_models.py smart-turn`.",
                resolved,
                cfg.candidate_min_silence_ms,
            )
            return None

        try:
            return cls(
                model_path=str(resolved),
                threshold=cfg.threshold,
                cpu_count=cfg.cpu_count,
                candidate_min_silence_ms=cfg.candidate_min_silence_ms,
                incomplete_delay_ms=cfg.incomplete_delay_ms,
            )
        except Exception:
            logger.warning(
                "Failed to load Smart Turn model from %s — endpointing falls back "
                "to the plain silence policy",
                resolved,
                exc_info=True,
            )
            return None

    @staticmethod
    def _prepare_audio(audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Resample to 16 kHz, then keep the last 8 s (left-pad if shorter)."""
        audio = np.asarray(audio, dtype=np.float32)
        if audio.ndim != 1:
            raise ValueError(f"Smart Turn expects mono 1-D audio, got shape {audio.shape}")
        if sample_rate <= 0:
            raise ValueError(f"Smart Turn sample rate must be positive, got {sample_rate}")

        if sample_rate != MODEL_SAMPLE_RATE:
            n_out = round(audio.size * MODEL_SAMPLE_RATE / sample_rate)
            if n_out > 0:
                src_idx = np.linspace(0, audio.size - 1, n_out)
                audio = np.interp(src_idx, np.arange(audio.size), audio).astype(
                    np.float32, copy=False,
                )
            else:
                audio = audio[:0]

        if audio.size > MAX_AUDIO_SAMPLES:
            return audio[-MAX_AUDIO_SAMPLES:]
        if audio.size < MAX_AUDIO_SAMPLES:
            return np.pad(audio, (MAX_AUDIO_SAMPLES - audio.size, 0), mode="constant")
        return audio

    def predict(
        self, audio_array: np.ndarray, *, sample_rate: int = MODEL_SAMPLE_RATE,
    ) -> SmartTurnResult:
        """Return whether ``audio_array`` sounds like a completed user turn."""
        started_at = time.perf_counter()
        audio = np.asarray(audio_array, dtype=np.float32)
        if audio.ndim != 1:
            raise ValueError(f"Smart Turn expects mono 1-D audio, got shape {audio.shape}")
        if audio.size < MIN_AUDIO_SAMPLES:
            return SmartTurnResult(
                complete=True, probability=1.0,
                inference_ms=(time.perf_counter() - started_at) * 1000,
            )

        audio = self._prepare_audio(audio, sample_rate)
        with self._lock:
            inputs = self._feature_extractor(
                audio,
                sampling_rate=MODEL_SAMPLE_RATE,
                return_tensors="np",
                padding="max_length",
                max_length=MAX_AUDIO_SAMPLES,
                truncation=True,
                do_normalize=True,
            )
            input_features = np.asarray(inputs.input_features, dtype=np.float32)
            if input_features.shape != EXPECTED_FEATURE_SHAPE:
                raise RuntimeError(
                    f"Smart Turn feature shape {input_features.shape} does not match "
                    f"the model contract {EXPECTED_FEATURE_SHAPE}"
                )
            outputs = self.session.run(None, {self._input_name: input_features})

        probability = float(np.asarray(outputs[0]).reshape(-1)[0])
        if not np.isfinite(probability):
            raise RuntimeError(f"Smart Turn returned a non-finite probability: {probability}")

        return SmartTurnResult(
            complete=probability > self.threshold,
            probability=probability,
            inference_ms=(time.perf_counter() - started_at) * 1000,
        )
