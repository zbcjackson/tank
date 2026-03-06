"""Abstract interface for speaker embedding extraction."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class SpeakerEmbeddingExtractor(ABC):
    """
    Abstract interface for speaker embedding extraction.

    Implementations can use different models (sherpa-onnx, pyannote, SpeechBrain, etc.)
    while maintaining a consistent interface.
    """

    @abstractmethod
    def extract(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Extract speaker embedding from audio.

        Args:
            audio: Audio samples (float32, shape: [n_samples])
            sample_rate: Sample rate in Hz

        Returns:
            Embedding vector (float32, shape: [embedding_dim])
        """
        pass

    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Return the dimension of the embedding vector."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Release resources (models, GPU memory, etc.)."""
        pass
