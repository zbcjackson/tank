"""TTS plugin contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioChunk:
    """One chunk of PCM audio for playback."""

    data: bytes
    sample_rate: int
    channels: int = 1


class TTSEngine(ABC):
    """Abstract TTS: text → stream of PCM chunks. Implement for each backend."""

    @abstractmethod
    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """
        Stream TTS for text. Yields PCM chunks as they are produced.
        If is_interrupted() becomes True, stop yielding and return.
        """
        ...
