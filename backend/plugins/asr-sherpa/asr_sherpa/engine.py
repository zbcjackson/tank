"""Sherpa-ONNX streaming ASR engine."""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

import numpy as np
from tank_contracts import StreamingASREngine

logger = logging.getLogger("SherpaASREngine")

# --- macOS Library Path Patch ---
if sys.platform == "darwin":
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


from sherpa_onnx.lib._sherpa_onnx import (  # noqa: E402
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


class SherpaASREngine(StreamingASREngine):
    """Streaming ASR using sherpa-onnx.

    Manages the sherpa-onnx OnlineRecognizer and its stream.
    """

    def __init__(
        self,
        model_dir: str,
        num_threads: int = 4,
        sample_rate: int = 16000,
    ):
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
        self._stream = self._recognizer.create_stream()
        self._sample_rate = sample_rate
        logger.info("SherpaASREngine initialized with model from %s", model_dir)

    def process_pcm(self, pcm: np.ndarray) -> tuple[str, bool]:
        """Process a chunk of PCM audio.

        Returns:
            (text, is_endpoint)
        """
        self._stream.accept_waveform(self._sample_rate, pcm)

        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)

        is_endpoint = self._recognizer.is_endpoint(self._stream)
        text = self._recognizer.get_result(self._stream).text.strip()

        if is_endpoint:
            self._recognizer.reset(self._stream)

        return text, is_endpoint

    def reset(self) -> None:
        """Reset the internal stream."""
        self._recognizer.reset(self._stream)
