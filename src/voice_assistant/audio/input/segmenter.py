"""Utterance segmentation using VAD and endpointing."""

from __future__ import annotations

import queue
from dataclasses import dataclass
import time

import numpy as np

from ...core.worker import QueueWorker
from ...core.shutdown import StopSignal

from .types import SegmenterConfig
from .mic import AudioFrame
from .vad import SileroVAD, VADStatus, VADResult


@dataclass
class Utterance:
    """Complete utterance audio segment."""
    pcm: np.ndarray  # full utterance audio float32
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
        self._vad = SileroVAD(cfg=cfg, sample_rate=16000)

    def handle(self, item: AudioFrame) -> None:
        """Handle one AudioFrame; may emit Utterance(s)."""
        result = self._vad.process_frame(
            pcm=item.pcm,
            timestamp_s=item.timestamp_s,
        )

        if result.status == VADStatus.END_SPEECH and result.utterance_pcm is not None:
            utterance = Utterance(
                pcm=result.utterance_pcm,
                sample_rate=result.sample_rate or item.sample_rate,
                started_at_s=result.started_at_s or item.timestamp_s,
                ended_at_s=result.ended_at_s or item.timestamp_s,
            )

            # Try to put utterance in queue with drop_oldest strategy
            try:
                self._utterance_queue.put_nowait(utterance)
            except queue.Full:
                # Queue is full - drop oldest and add new one
                try:
                    self._utterance_queue.get_nowait()  # Remove oldest
                    self._utterance_queue.put_nowait(utterance)  # Add new
                except queue.Empty:
                    # Queue became empty between checks, just add
                    self._utterance_queue.put_nowait(utterance)

    def cleanup(self) -> None:
        """Cleanup on shutdown - flush any in-progress speech."""
        # Flush any in-progress speech
        now_s = time.time()
        result = self._vad.flush(now_s=now_s)

        if result.status == VADStatus.END_SPEECH and result.utterance_pcm is not None:
            utterance = Utterance(
                pcm=result.utterance_pcm,
                sample_rate=result.sample_rate or 16000,
                started_at_s=result.started_at_s or now_s,
                ended_at_s=result.ended_at_s or now_s,
            )

            # Try to put final utterance in queue
            try:
                self._utterance_queue.put_nowait(utterance)
            except queue.Full:
                # Queue is full - drop oldest and add new one
                try:
                    self._utterance_queue.get_nowait()  # Remove oldest
                    self._utterance_queue.put_nowait(utterance)  # Add new
                except queue.Empty:
                    # Queue became empty between checks, just add
                    self._utterance_queue.put_nowait(utterance)
