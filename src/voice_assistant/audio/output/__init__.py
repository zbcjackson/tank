"""Audio output subsystem - TTS and playback."""

from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Optional

from ...core.shutdown import GracefulShutdown

from .speaker import SpeakerHandler


@dataclass(frozen=True)
class AudioOutputConfig:
    """Configuration for Audio output subsystem."""
    # Future: TTS voice selection, playback device, etc.
    pass


class AudioOutput:
    """
    Audio output subsystem facade.
    
    Responsibilities:
    - Text-to-speech conversion
    - Audio playback with interruption support
    
    All audio output processing is encapsulated here.
    """

    def __init__(
        self,
        shutdown_signal: GracefulShutdown,
        audio_output_queue: "queue.Queue[dict]",
        cfg: AudioOutputConfig = AudioOutputConfig(),
    ):
        self._shutdown_signal = shutdown_signal
        self._cfg = cfg

        # Thread
        self._speaker = SpeakerHandler(
            shutdown_signal=shutdown_signal,
            audio_output_queue=audio_output_queue,
        )

    @property
    def speaker(self) -> SpeakerHandler:
        """Access to speaker for interruption control."""
        return self._speaker

    def start(self) -> None:
        """Start audio output thread."""
        self._speaker.start()

    def join(self) -> None:
        """Wait for audio output thread to finish."""
        self._speaker.join()


__all__ = [
    "AudioOutput",
    "AudioOutputConfig",
    "SpeakerHandler",
]
