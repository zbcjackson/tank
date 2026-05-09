"""Sherpa-ONNX streaming ASR engine.

Split into two layers:

* ``SherpaASREngine`` — loads the ``OnlineRecognizer`` (and its ONNX models)
  once per process, creates cheap streams.
* ``SherpaASRStream`` — per-utterance decoding state (the sherpa stream object,
  session flag, last-seen text).
"""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from tank_contracts import ASREngine, ASRStream

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger("SherpaASREngine")


def _patch_macos_onnxruntime() -> None:
    """Pre-load onnxruntime dylib on macOS to avoid sherpa-onnx load failures."""
    if sys.platform != "darwin":
        return
    try:
        import onnxruntime

        ort_dir = Path(onnxruntime.__file__).parent
        possible_paths = [
            ort_dir / "capi" / "libonnxruntime.1.23.2.dylib",
            ort_dir / "capi" / "libonnxruntime.dylib",
        ]
        for dylib_path in possible_paths:
            if dylib_path.exists():
                ctypes.CDLL(str(dylib_path))
                logger.debug(f"Successfully pre-loaded onnxruntime from {dylib_path}")
                break
    except Exception as e:
        logger.debug(f"macOS dylib patch failed: {e}")


def _load_sherpa():
    """Load sherpa-onnx symbols after applying macOS compatibility patch."""
    _patch_macos_onnxruntime()
    from sherpa_onnx.lib._sherpa_onnx import (
        EndpointConfig,
        EndpointRule,
        FeatureExtractorConfig,
        OnlineCtcFstDecoderConfig,
        OnlineLMConfig,
        OnlineModelConfig,
        OnlineRecognizer,
        OnlineRecognizerConfig,
        OnlineTransducerModelConfig,
    )
    return (
        EndpointConfig, EndpointRule, FeatureExtractorConfig,
        OnlineCtcFstDecoderConfig, OnlineLMConfig, OnlineModelConfig,
        OnlineRecognizer, OnlineRecognizerConfig, OnlineTransducerModelConfig,
    )


class SherpaASRStream(ASRStream):
    """Per-utterance sherpa-onnx recognition session.

    Holds a fresh sherpa stream (from ``recognizer.create_stream()``) and
    tracks session state. The underlying model lives on the engine.
    """

    def __init__(self, engine: SherpaASREngine) -> None:
        self._engine = engine
        self._recognizer = engine._recognizer
        self._stream = self._recognizer.create_stream()
        self._sample_rate = engine._sample_rate
        self._session_active = False
        self._last_text = ""

    def start(self) -> None:
        """Start a new recognition session."""
        self._recognizer.reset(self._stream)
        self._session_active = True
        self._last_text = ""
        logger.debug("Sherpa: Session started")

    def process_pcm(self, pcm: np.ndarray) -> str:
        """Process a chunk of PCM audio.

        Returns:
            Current partial transcript text.
        """
        if not self._session_active:
            logger.warning("Sherpa: process_pcm called without active session")
            return ""

        self._stream.accept_waveform(self._sample_rate, pcm)

        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)

        text = self._recognizer.get_result(self._stream).text.strip()

        if text:
            self._last_text = text

        return text

    def stop(self) -> str:
        """Stop the session and return final transcript."""
        if not self._session_active:
            logger.warning("Sherpa: stop called without active session")
            return ""

        self._session_active = False

        text = self._recognizer.get_result(self._stream).text.strip()
        final_text = text or self._last_text

        self._recognizer.reset(self._stream)
        self._last_text = ""

        logger.debug("Sherpa: Session stopped, final text: %s", final_text[:50] if final_text else "(empty)")
        return final_text

    def close(self) -> None:
        """Release per-session resources (no-op for local model)."""
        self._session_active = False


class SherpaASREngine(ASREngine):
    """Process-global sherpa-onnx engine. Owns the OnlineRecognizer + ONNX models.

    Create once at startup, then call ``create_stream()`` per utterance.
    """

    def __init__(
        self,
        model_dir: str,
        num_threads: int = 4,
        sample_rate: int = 16000,
    ):
        (
            EndpointConfig, EndpointRule, FeatureExtractorConfig,
            OnlineCtcFstDecoderConfig, OnlineLMConfig, OnlineModelConfig,
            OnlineRecognizer, OnlineRecognizerConfig, OnlineTransducerModelConfig,
        ) = _load_sherpa()

        model_path = Path(model_dir)
        if not model_path.exists():
            raise FileNotFoundError(f"Sherpa-ONNX model directory not found: {model_dir}")

        feat_config = FeatureExtractorConfig(
            sampling_rate=sample_rate,
            feature_dim=80,
        )

        transducer_config = OnlineTransducerModelConfig(
            encoder=str(model_path / "encoder-epoch-99-avg-1.onnx"),
            decoder=str(model_path / "decoder-epoch-99-avg-1.onnx"),
            joiner=str(model_path / "joiner-epoch-99-avg-1.onnx"),
        )

        model_config = OnlineModelConfig(
            transducer=transducer_config,
            tokens=str(model_path / "tokens.txt"),
            num_threads=num_threads,
            model_type="zipformer",
        )

        endpoint_config = EndpointConfig(
            rule1=EndpointRule(False, 2.4, 0.0),
            rule2=EndpointRule(True, 1.2, 0.0),
            rule3=EndpointRule(False, 20.0, 0.0),
        )

        recognizer_config = OnlineRecognizerConfig(
            feat_config,
            model_config,
            OnlineLMConfig(),
            endpoint_config,
            OnlineCtcFstDecoderConfig(),
            True,  # enable_endpoint
            "greedy_search",  # decoding_method
        )

        self._recognizer = OnlineRecognizer(recognizer_config)
        self._sample_rate = sample_rate
        logger.info("SherpaASREngine initialized with model from %s", model_dir)

    def create_stream(self) -> ASRStream:
        """Create a fresh per-utterance recognition stream."""
        return SherpaASRStream(self)

    def close(self) -> None:
        """Release engine-level resources (no-op for local model)."""
        logger.info("Sherpa: Engine closed")
