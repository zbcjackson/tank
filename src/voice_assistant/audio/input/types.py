"""Audio input subsystem data types and configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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
