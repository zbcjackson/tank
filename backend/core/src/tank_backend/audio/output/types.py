"""Audio output data types."""

from __future__ import annotations

import queue
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from tank_contracts.tts import AudioChunk

from ...core.shutdown import StopSignal


@runtime_checkable
class AudioSink(Protocol):
    """Protocol for audio output destinations."""

    def start(self) -> None:
        """Start playing audio."""
        ...

    def join(self, timeout: float | None = None) -> None:
        """Wait for the sink to stop."""
        ...


AudioSinkFactory = Callable[[queue.Queue[AudioChunk | None], StopSignal], AudioSink]

__all__ = ["AudioChunk", "AudioSink", "AudioSinkFactory"]
