"""Speaker embedding extraction using sherpa-onnx."""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

import numpy as np
from tank_contracts import SpeakerEmbeddingExtractor

logger = logging.getLogger("SherpaEmbedding")


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
        SpeakerEmbeddingExtractor as _SherpaExtractor,
        SpeakerEmbeddingExtractorConfig,
    )
    return _SherpaExtractor, SpeakerEmbeddingExtractorConfig


class SherpaEmbeddingExtractor(SpeakerEmbeddingExtractor):
    """Speaker embedding extraction using sherpa-onnx.

    Supports models like 3D-Speaker (Alibaba) and WeSpeaker in ONNX format.
    """

    def __init__(self, model_path: str, num_threads: int = 1, provider: str = "cpu"):
        _SherpaExtractor, SpeakerEmbeddingExtractorConfig = _load_sherpa()

        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"Speaker model not found: {model_path}")

        config = SpeakerEmbeddingExtractorConfig(
            model=str(model_file),
            num_threads=num_threads,
            provider=provider,
        )
        self._extractor = _SherpaExtractor(config)
        self._dim = self._extractor.dim
        logger.info(f"Sherpa embedding extractor initialized (dim={self._dim})")

    def extract(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        max_val = np.abs(audio).max()
        if max_val > 1.0:
            audio = audio / max_val

        stream = self._extractor.create_stream()
        stream.accept_waveform(sample_rate=sample_rate, waveform=audio)

        embedding = self._extractor.compute(stream)
        return np.array(embedding, dtype=np.float32)

    @property
    def embedding_dim(self) -> int:
        return self._dim

    def close(self) -> None:
        pass
