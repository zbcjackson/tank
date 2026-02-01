"""TTS abstraction: protocol only, no dependency on edge_tts."""

from __future__ import annotations

from typing import AsyncIterator, Callable, Optional, Protocol

from .types import AudioChunk


class TTSEngine(Protocol):
    """Abstract TTS: text → stream of PCM chunks."""

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: Optional[str] = None,
        is_interrupted: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[AudioChunk]:
        """
        Stream TTS for text. Yields PCM chunks.
        If is_interrupted() becomes True, stop yielding and return.
        """
        ...
