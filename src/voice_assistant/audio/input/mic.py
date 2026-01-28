"""Microphone audio capture."""

from __future__ import annotations

import threading
import queue
from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np

from .types import AudioFormat, FrameConfig


class StopSignal(Protocol):
    """Protocol for shutdown signal."""
    def is_set(self) -> bool: ...


@dataclass
class AudioFrame:
    """Single audio frame from microphone."""
    pcm: np.ndarray          # shape: (n_samples,) float32
    sample_rate: int
    timestamp_s: float


class Mic(threading.Thread):
    """
    Continuously captures microphone audio and pushes AudioFrame into frames_queue.

    Important: keep callback/lightweight; no VAD/ASR here.
    """

    def __init__(
        self,
        stop_signal: StopSignal,
        audio_format: AudioFormat,
        frame_cfg: FrameConfig,
        frames_queue: queue.Queue[AudioFrame],
        device: Optional[int] = None,
    ):
        super().__init__(name="MicThread", daemon=True)
        self._stop_signal = stop_signal
        self._audio_format = audio_format
        self._frame_cfg = frame_cfg
        self._frames_queue = frames_queue
        self._device = device

    def run(self) -> None:
        """Start microphone capture loop."""
        raise NotImplementedError("Mic capture not implemented in skeleton.")
