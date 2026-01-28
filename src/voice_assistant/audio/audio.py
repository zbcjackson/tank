"""Audio subsystem facade - captures audio, segments, and recognizes speech."""

from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Optional

from voice_assistant.core.shutdown import GracefulShutdown
from voice_assistant.core.runtime import RuntimeContext

from .types import AudioFormat, FrameConfig, SegmenterConfig
from .mic import Mic, AudioFrame
from .segmenter import UtteranceSegmenter, Utterance
from .perception import Perception, PerceptionConfig


@dataclass(frozen=True)
class AudioConfig:
    """Configuration for Audio subsystem."""
    audio_format: AudioFormat = AudioFormat()
    frame: FrameConfig = FrameConfig()
    segmenter: SegmenterConfig = SegmenterConfig()
    perception: PerceptionConfig = PerceptionConfig()
    input_device: Optional[int] = None


class Audio:
    """
    Audio subsystem facade.
    
    Responsibilities:
    - Microphone capture (Mic thread)
    - Utterance segmentation using VAD (UtteranceSegmenter thread)
    - Speech recognition and voiceprint (Perception thread)
    
    All audio-related processing is encapsulated here.
    core/Assistant should only call start/stop and never touch audio internals directly.
    """

    def __init__(
        self,
        shutdown_signal: GracefulShutdown,
        runtime: RuntimeContext,
        cfg: AudioConfig,
    ):
        self._shutdown_signal = shutdown_signal
        self._runtime = runtime
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
        self._perception = Perception(
            shutdown_signal=shutdown_signal,
            runtime=runtime,
            utterance_queue=self._utterance_queue,
            config=cfg.perception,
        )

    def start(self) -> None:
        """Start all audio threads (mic, segmenter, perception)."""
        self._mic.start()
        self._segmenter.start()
        self._perception.start()

    def join(self) -> None:
        """Wait for all audio threads to finish."""
        self._mic.join()
        self._segmenter.join()
        self._perception.join()
