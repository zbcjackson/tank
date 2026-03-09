"""ASR (Automatic Speech Recognition) plugin contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class StreamingASREngine(ABC):
    """Abstract streaming ASR: process PCM chunks and detect endpoints."""

    @abstractmethod
    def process_pcm(self, pcm: np.ndarray) -> tuple[str, bool]:
        """Process a chunk of PCM audio.

        Args:
            pcm: Float32 mono audio samples.

        Returns:
            (text, is_endpoint) — partial/final transcript and whether
            the recognizer detected an utterance boundary.
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state for a new utterance."""
        ...
