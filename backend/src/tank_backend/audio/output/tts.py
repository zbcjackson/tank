"""TTS abstraction: ABC for engines, no dependency on edge_tts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Callable, Optional

from .types import AudioChunk


class TTSEngine(ABC):
    """Abstract TTS: text → stream of PCM chunks. Implement for each backend."""

    @abstractmethod
    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: Optional[str] = None,
        is_interrupted: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[AudioChunk]:
        """
        Stream TTS for text. Yields PCM chunks as they are produced.
        If is_interrupted() becomes True, stop yielding and return.
        """
        ...
