"""Audio subsystem - input (capture/recognition) and output (TTS/playback)."""

from .input import (
    AudioFormat,
    FrameConfig,
    PerceptionConfig,
    SegmenterConfig,
)

__all__ = [
    "AudioFormat",
    "FrameConfig",
    "SegmenterConfig",
    "PerceptionConfig",
]
