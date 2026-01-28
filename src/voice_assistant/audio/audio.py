"""Audio subsystem facade - captures audio and segments into utterances."""

from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Optional

from voice_assistant.core.shutdown import GracefulShutdown

from .types import AudioFormat, FrameConfig, SegmenterConfig
from .mic import Mic, AudioFrame
from .segmenter import UtteranceSegmenter, Utterance


@dataclass(frozen=True)
class AudioConfig:
    """Configuration for Audio subsystem."""
    audio_format: AudioFormat = AudioFormat()
    frame: FrameConfig = FrameConfig()
    segmenter: SegmenterConfig = SegmenterConfig()
    input_device: Optional[int] = None


class Audio:
    """
    Audio subsystem facade.
    
    Responsibilities:
    - Microphone capture (Mic thread)
    - Utterance segmentation using VAD (UtteranceSegmenter thread)
    
    Output: Utterance items in utterance_queue (consumed by Perception thread).
    
    core/Assistant should only call start/stop and never touch audio queues directly.
    """

    def __init__(self, shutdown_signal: GracefulShutdown, cfg: AudioConfig):
        self._shutdown_signal = shutdown_signal
        self._cfg = cfg

        # Internal queues (not exposed to core)
        self._frames_queue: queue.Queue[AudioFrame] = queue.Queue(
            maxsize=cfg.frame.max_frames_queue
        )
        self._utterance_queue: queue.Queue[Utterance] = queue.Queue(maxsize=20)

        # Threads
        self._mic = Mic(
            stop_signal=shutdown_signal,
            audio_format=cfg.audio_format,
            frame_cfg=cfg.frame,
            frames_queue=self._frames_queue,
            device=cfg.input_device,
        )
        self._segmenter = UtteranceSegmenter(
            stop_signal=shutdown_signal,
            cfg=cfg.segmenter,
            frames_queue=self._frames_queue,
            utterance_queue=self._utterance_queue,
        )

    @property
    def utterance_queue(self) -> queue.Queue[Utterance]:
        """
        Queue containing segmented utterances.
        Intended for Perception thread consumption.
        """
        return self._utterance_queue

    def start(self) -> None:
        """Start all audio threads."""
        self._mic.start()
        self._segmenter.start()

    def join(self) -> None:
        """Wait for all audio threads to finish."""
        self._mic.join()
        self._segmenter.join()
