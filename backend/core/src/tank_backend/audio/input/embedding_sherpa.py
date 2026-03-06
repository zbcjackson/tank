"""Speaker embedding extraction using sherpa-onnx."""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger("SherpaEmbedding")

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


from sherpa_onnx.lib._sherpa_onnx import (  # noqa: E402, I001
    SpeakerEmbeddingExtractor as _SherpaExtractor,
    SpeakerEmbeddingExtractorConfig,
)

from .embedding import SpeakerEmbeddingExtractor  # noqa: E402, I001


class SherpaEmbeddingExtractor(SpeakerEmbeddingExtractor):
    """
    Speaker embedding extraction using sherpa-onnx.

    Supports models like 3D-Speaker (Alibaba) and WeSpeaker in ONNX format.
    """

    def __init__(self, model_path: str, num_threads: int = 1, provider: str = "cpu"):
        """
        Initialize Sherpa-ONNX speaker embedding extractor.

        Args:
            model_path: Path to ONNX model file (e.g., 3D-Speaker or WeSpeaker)
            num_threads: Number of threads for inference
            provider: Execution provider ("cpu" or "cuda")

        Raises:
            FileNotFoundError: If model file does not exist
        """
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
        logger.info(f"Sherpa embedding extractor initialized (dim={self._dim}, model={model_path})")

    def extract(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Extract speaker embedding from audio.

        Args:
            audio: Audio samples (float32, shape: [n_samples])
            sample_rate: Sample rate in Hz

        Returns:
            Embedding vector (float32, shape: [embedding_dim])
        """
        # Sherpa expects float32 in range [-1, 1]
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Normalize to [-1, 1] if needed
        max_val = np.abs(audio).max()
        if max_val > 1.0:
            audio = audio / max_val

        # Create stream and feed audio
        stream = self._extractor.create_stream()
        stream.accept_waveform(sample_rate=sample_rate, waveform=audio)

        # Extract embedding
        embedding = self._extractor.compute(stream)
        return np.array(embedding, dtype=np.float32)

    @property
    def embedding_dim(self) -> int:
        """Return the dimension of the embedding vector."""
        return self._dim

    def close(self) -> None:
        """Release resources."""
        # Sherpa-ONNX handles cleanup automatically via RAII
        pass
