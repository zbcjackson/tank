"""ASR (Automatic Speech Recognition) plugin contract.

Two-tier abstraction:

* ``ASREngine`` — process-global, owns loaded models, exposes ``create_stream()``
  and ``transcribe_once()``. One per process.
* ``ASRStream`` — per-utterance recognition session, cheap to create.

For backward compatibility, ``StreamingASREngine`` is kept as an alias for
``ASRStream``; existing plugins that still subclass it continue to work for
one release.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class ASRStream(ABC):
    """Abstract per-utterance ASR session with explicit lifecycle.

    Lifecycle:
        1. start()      - Begin a recognition session (called on VAD speech start)
        2. process_pcm() - Stream audio chunks during speech
        3. stop()       - End session and get final transcript (called on VAD speech end)
        4. close()      - Release per-session resources

    An ``ASRStream`` instance is obtained from ``ASREngine.create_stream()``.
    Streams should be cheap — the model is owned by the engine.
    """

    @abstractmethod
    def start(self) -> None:
        """Start a new recognition session.

        Called when VAD detects speech start. The stream should prepare
        to receive audio chunks via process_pcm().
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

        Called when VAD detects speech end. The stream should:
        1. Flush any buffered audio
        2. Wait for final results (for async/cloud engines)
        3. Clean up session resources
        4. Return the final, complete transcript
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Release per-session resources.

        Engine-owned resources (models, shared connections) are released
        via ``ASREngine.close()``; ``ASRStream.close()`` is cheap and
        concerns only per-session state.
        """
        ...

    @property
    def supports_streaming(self) -> bool:
        """Whether this stream produces meaningful partial transcripts.

        Streams that return True can receive small PCM chunks via process_pcm
        during speech. Streams that return False (e.g. batch-only Whisper)
        should only be called with a complete utterance after VAD END_SPEECH.
        """
        return True


class ASREngine(ABC):
    """Abstract process-global ASR engine.

    Owns loaded ASR models (or persistent connections for cloud engines)
    and creates cheap per-utterance ``ASRStream`` instances.
    """

    @abstractmethod
    def create_stream(self) -> ASRStream:
        """Create a fresh per-utterance recognition stream.

        Streams are cheap — the model (or shared connection) is owned by
        the engine. Callers are responsible for calling ``stream.close()``
        when the session ends.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Release engine-level resources (models, shared connections).

        Called on application shutdown. After close(), no further streams
        should be created.
        """
        ...

    async def transcribe_once(
        self,
        pcm: np.ndarray,
        sample_rate: int = 16000,  # noqa: ARG002 — reserved for future resampling
    ) -> str:
        """Transcribe a single complete utterance.

        Convenience wrapper for one-shot transcription (e.g. a platform
        voice note) that doesn't need to manage stream lifecycle. Creates
        a short-lived stream, runs the full cycle, and returns the final
        transcript.
        """
        stream = self.create_stream()
        try:
            stream.start()
            stream.process_pcm(pcm)
            return stream.stop()
        finally:
            stream.close()


# Backward-compatible alias. Plugins subclassing StreamingASREngine continue to
# work without immediate changes; they are semantically per-utterance streams.
StreamingASREngine = ASRStream
