"""Audio input subsystem data types and configuration."""

from __future__ import annotations

import queue
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from ...core.shutdown import StopSignal


@dataclass
class AudioFrame:
    """Single audio frame from microphone or other source."""

    pcm: np.ndarray  # shape: (n_samples,) float32
    sample_rate: int
    timestamp_s: float


@runtime_checkable
class AudioSource(Protocol):
    """Protocol for audio input sources."""

    def start(self) -> None:
        """Start capturing audio."""
        ...

    def join(self, timeout: float | None = None) -> None:
        """Wait for the source to stop."""
        ...


AudioSourceFactory = Callable[[queue.Queue["AudioFrame"], StopSignal], AudioSource]


@dataclass(frozen=True)
class AudioFormat:
    """Audio format specification."""

    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "float32"  # sounddevice dtype name


@dataclass(frozen=True)
class FrameConfig:
    """Frame-level audio processing configuration."""

    frame_ms: int = 20
    max_frames_queue: int = 400


@dataclass(frozen=True)
class SegmenterConfig:
    """Utterance segmentation (VAD + endpointing) configuration."""

    speech_threshold: float = 0.5
    min_speech_ms: int = 200
    min_silence_ms: int = 1000
    pre_roll_ms: int = 200
    max_utterance_ms: int = 20000


@dataclass(frozen=True)
class PerceptionConfig:
    """Configuration for Perception thread."""

    enable_voiceprint: bool = True
    voiceprint_timeout_s: float = 0.5
    default_user: str = "Unknown"
