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

    @property
    def supports_streaming(self) -> bool:
        """Whether this engine supports streaming frame-by-frame recognition.

        Engines that return True can receive small PCM chunks via process_pcm
        during speech and produce meaningful partial transcripts.
        Engines that return False (e.g. batch-only Whisper) should only be
        called with a complete utterance after VAD END_SPEECH.
        """
        return True

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state for a new utterance."""
        ...
