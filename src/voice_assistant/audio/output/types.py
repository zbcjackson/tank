"""Audio output data types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AudioOutputRequest:
    """Single item for audio output queue: text to speak."""

    content: str
    language: str = "auto"
    voice: Optional[str] = None


@dataclass(frozen=True)
class AudioChunk:
    """One chunk of PCM audio for playback."""

    data: bytes
    sample_rate: int
    channels: int = 1
