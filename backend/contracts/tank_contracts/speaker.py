"""Speaker embedding extraction plugin contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class SpeakerEmbeddingExtractor(ABC):
    """Abstract speaker embedding extractor. Implement for each backend."""

    @abstractmethod
    def extract(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Extract speaker embedding from audio.

        Args:
            audio: Audio samples (float32, shape: [n_samples])
            sample_rate: Sample rate in Hz

        Returns:
            Embedding vector (float32, shape: [embedding_dim])
        """
        ...

    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Return the dimension of the embedding vector."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release resources (models, GPU memory, etc.)."""
        ...
