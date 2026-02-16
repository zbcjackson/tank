import queue
from dataclasses import dataclass
from typing import Callable, Optional

from ...core.shutdown import GracefulShutdown
from ...core.runtime import RuntimeContext
from .types import AudioFormat, FrameConfig, PerceptionConfig, AudioSource, AudioFrame, AudioSourceFactory
from .mic import Mic
from .asr_sherpa import SherpaASR
from .perception_streaming import StreamingPerception

@dataclass(frozen=True)
class AudioInputConfig:
    """Configuration for Audio input subsystem."""
    audio_format: AudioFormat = AudioFormat()
    frame: FrameConfig = FrameConfig()
    perception: PerceptionConfig = PerceptionConfig()
    input_device: Optional[int] = None

class AudioInput:
    """
    Audio input subsystem facade.

    Responsibilities:
    - Microphone capture (or other AudioSource)
    - Streaming Speech recognition (StreamingPerception thread)

    Simplifies the pipeline to Source -> StreamingPerception for minimal latency.
    """

    def __init__(
            self,
            shutdown_signal: GracefulShutdown,
            runtime: RuntimeContext,
            cfg: AudioInputConfig,
            on_speech_interrupt: Optional[Callable[[], None]] = None,
            source_factory: Optional[AudioSourceFactory] = None,
    ):
        self._shutdown_signal = shutdown_signal
        self._runtime = runtime
        self._cfg = cfg

        # Single queue for perception
        self._frames_queue: queue.Queue[AudioFrame] = queue.Queue(
            maxsize=cfg.frame.max_frames_queue
        )
        
        # Use provided source factory or default to Mic
        if source_factory is not None:
            self._source = source_factory(self._frames_queue, self._shutdown_signal)
        else:
            self._source = Mic(
                stop_signal=shutdown_signal,
                audio_format=cfg.audio_format,
                frame_cfg=cfg.frame,
                frames_queue=self._frames_queue,
                device=cfg.input_device,
            )
        
        # Use SherpaASR for streaming
        asr = SherpaASR(model_dir=cfg.perception.sherpa_model_dir)
        
        self._perception = StreamingPerception(
            shutdown_signal=shutdown_signal,
            runtime=runtime,
            frames_queue=self._frames_queue,
            asr=asr,
            user=cfg.perception.default_user,
            on_speech_interrupt=on_speech_interrupt,
        )

    def start(self) -> None:
        """Start source and streaming perception."""
        self._source.start()
        self._perception.start()

    def join(self) -> None:
        """Wait for threads to finish."""
        self._source.join()
        self._perception.join()