"""Audio output subsystem facade."""

from __future__ import annotations

import logging
import queue
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...config.settings import VoiceAssistantConfig
from ...core.events import AudioOutputRequest
from ...core.shutdown import GracefulShutdown
from .playback_worker import PlaybackWorker
from .tts_engine_edge import EdgeTTSEngine
from .tts_worker import TTSWorker
from .types import AudioChunk, AudioSink, AudioSinkFactory

if TYPE_CHECKING:
    from ...core.runtime import RuntimeContext

logger = logging.getLogger("Speaker")


@dataclass(frozen=True)
class AudioOutputConfig:
    """Configuration for Audio output subsystem."""

    # Future: TTS voice selection, playback device, etc.
    pass


class AudioOutput:
    """
    Audio output subsystem facade.

    Two threads: TTSWorker (request -> chunks) and Sink (chunks -> destination).
    interrupt() sets runtime.interrupt_event and clears queues so playback stops quickly.
    """

    def __init__(
        self,
        shutdown_signal: GracefulShutdown,
        runtime: "RuntimeContext",
        audio_output_queue: "queue.Queue[AudioOutputRequest]",
        config: VoiceAssistantConfig,
        cfg: AudioOutputConfig = AudioOutputConfig(),
        sink_factory: Optional[AudioSinkFactory] = None,
    ):
        self._shutdown_signal = shutdown_signal
        self._runtime = runtime
        self._cfg = cfg
        self._audio_chunk_queue: "queue.Queue[AudioChunk | None]" = queue.Queue(maxsize=20)
        tts_engine = EdgeTTSEngine(config)
        self._tts_worker = TTSWorker(
            name="TTSThread",
            stop_signal=shutdown_signal,
            input_queue=audio_output_queue,
            audio_chunk_queue=self._audio_chunk_queue,
            tts_engine=tts_engine,
            interrupt_event=runtime.interrupt_event,
        )
        
        if sink_factory is not None:
            self._sink = sink_factory(self._audio_chunk_queue, self._shutdown_signal)
        else:
            self._sink = PlaybackWorker(
                name="PlaybackThread",
                stop_signal=shutdown_signal,
                audio_chunk_queue=self._audio_chunk_queue,
                interrupt_event=runtime.interrupt_event,
            )

    @property
    def speaker(self) -> "AudioOutput":
        """Access for interruption control (e.g. speaker.interrupt())."""

        return self

    def interrupt(self) -> None:
        """Interrupt current playback: set interrupt event and clear pending requests."""

        self._runtime.interrupt_event.set()
        with self._runtime.audio_output_queue.mutex:
            self._runtime.audio_output_queue.queue.clear()
        logger.warning("Speaker interrupted")

    def cancel(self) -> None:
        """Cancel the currently running TTS task (for graceful disconnect)."""
        self._tts_worker.cancel()

    def start(self) -> None:
        """Start TTS and sink threads."""

        self._tts_worker.start()
        self._sink.start()

    def join(self) -> None:
        """Wait for both threads to finish."""

        self._tts_worker.join()
        self._sink.join()

