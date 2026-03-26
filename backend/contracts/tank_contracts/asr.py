"""ASR (Automatic Speech Recognition) plugin contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class StreamingASREngine(ABC):
    """Abstract streaming ASR engine with explicit session lifecycle.

    Lifecycle:
        1. start()      - Begin a recognition session (called on VAD speech start)
        2. process_pcm() - Stream audio chunks during speech
        3. stop()       - End session and get final transcript (called on VAD speech end)
        4. close()      - Release resources (called on app shutdown)

    The engine should be reusable: start() → process_pcm() → stop() can be
    repeated multiple times before close().
    """

    @abstractmethod
    def start(self) -> None:
        """Start a new recognition session.

        Called when VAD detects speech start. The engine should prepare
        to receive audio chunks via process_pcm().

        For cloud APIs, this might establish a connection or start a session.
        For local models, this might reset internal buffers.
        """
        ...

    @abstractmethod
    def process_pcm(self, pcm: np.ndarray) -> str:
        """Process a chunk of PCM audio during an active session.

        Args:
            pcm: Float32 mono audio samples.

        Returns:
            Current partial transcript text.
        """
        ...

    @abstractmethod
    def stop(self) -> str:
        """Stop the recognition session and return the final transcript.

        Called when VAD detects speech end. The engine should:
        1. Flush any buffered audio
        2. Wait for final results (for async/cloud engines)
        3. Clean up session resources
        4. Return the final, complete transcript

        Returns:
            The final transcript for this utterance.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Release all resources.

        Called on application shutdown. After close(), the engine
        should not be used again.
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

