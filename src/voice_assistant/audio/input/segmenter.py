"""Utterance segmentation using VAD and endpointing."""

from __future__ import annotations

import queue
from dataclasses import dataclass

import numpy as np

from ...core.worker import QueueWorker
from ...core.shutdown import StopSignal

from .types import SegmenterConfig
from .mic import AudioFrame


@dataclass
class Utterance:
    """Complete utterance audio segment."""
    pcm: np.ndarray          # full utterance audio float32
    sample_rate: int
    started_at_s: float
    ended_at_s: float


class UtteranceSegmenter(QueueWorker[AudioFrame]):
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
        super().__init__(
            name="UtteranceSegmenterThread",
            stop_signal=stop_signal,
            input_queue=frames_queue,
            poll_interval_s=0.1,
        )
        self._cfg = cfg
        self._utterance_queue = utterance_queue

    def handle(self, item: AudioFrame) -> None:
        """Handle one AudioFrame; may emit Utterance(s)."""
        raise NotImplementedError("VAD/segmenting not implemented in skeleton.")
