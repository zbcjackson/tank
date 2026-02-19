"""Audio output data types."""

from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Protocol, runtime_checkable, Callable, Optional


from ...core import StopSignal


@runtime_checkable
class AudioSink(Protocol):
    """Protocol for audio output destinations."""
    def start(self) -> None:
        """Start playing audio."""
        ...

    def join(self) -> None:
        """Wait for the sink to stop."""
        ...


AudioSinkFactory = Callable[[queue.Queue[Optional["AudioChunk"]], StopSignal], AudioSink]


@dataclass(frozen=True)
class AudioChunk:
    """One chunk of PCM audio for playback."""

    data: bytes
    sample_rate: int
    channels: int = 1
