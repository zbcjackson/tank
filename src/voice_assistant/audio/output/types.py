"""Audio output data types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioChunk:
    """One chunk of PCM audio for playback."""

    data: bytes
    sample_rate: int
    channels: int = 1
