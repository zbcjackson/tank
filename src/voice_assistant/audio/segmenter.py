"""Utterance segmentation using VAD and endpointing."""

from __future__ import annotations

import threading
import queue
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .types import SegmenterConfig
from .mic import AudioFrame


class StopSignal(Protocol):
    """Protocol for shutdown signal."""
    def is_set(self) -> bool: ...


@dataclass
class Utterance:
    """Complete utterance audio segment."""
    pcm: np.ndarray          # full utterance audio float32
    sample_rate: int
    started_at_s: float
    ended_at_s: float


class UtteranceSegmenter(threading.Thread):
    """
    Consumes AudioFrame stream and produces Utterance items using VAD + endpointing.
    (silero-vad torch or ONNX can be used internally.)
    """

    def __init__(
        self,
        stop_signal: StopSignal,
        cfg: SegmenterConfig,
        frames_queue: queue.Queue[AudioFrame],
        utterance_queue: queue.Queue[Utterance],
    ):
        super().__init__(name="UtteranceSegmenterThread", daemon=True)
        self._stop_signal = stop_signal
        self._cfg = cfg
        self._frames_queue = frames_queue
        self._utterance_queue = utterance_queue

    def run(self) -> None:
        """Start segmentation loop."""
        raise NotImplementedError("VAD/segmenting not implemented in skeleton.")
