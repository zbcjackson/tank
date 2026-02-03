"""Audio output subsystem - TTS and playback."""

from __future__ import annotations

import queue
from dataclasses import dataclass

from ...config.settings import VoiceAssistantConfig
from ...core.events import AudioOutputRequest
from ...core.shutdown import GracefulShutdown
from .speaker import PlaybackWorker, TTSWorker
from .tts_engine_edge import EdgeTTSEngine
from .types import AudioChunk


@dataclass(frozen=True)
class AudioOutputConfig:
    """Configuration for Audio output subsystem."""
    # Future: TTS voice selection, playback device, etc.
    pass


class AudioOutput:
    """
    Audio output subsystem facade.

    Two threads: TTSWorker (request -> chunks) and PlaybackWorker (chunks -> device).
    Interruption not implemented yet; interrupt() is a no-op.
    """

    def __init__(
        self,
        shutdown_signal: GracefulShutdown,
        audio_output_queue: "queue.Queue[AudioOutputRequest]",
        config: VoiceAssistantConfig,
        cfg: AudioOutputConfig = AudioOutputConfig(),
    ):
        self._shutdown_signal = shutdown_signal
        self._cfg = cfg
        self._audio_chunk_queue: "queue.Queue[AudioChunk | None]" = queue.Queue(maxsize=20)
        tts_engine = EdgeTTSEngine(config)
        self._tts_worker = TTSWorker(
            name="TTSThread",
            stop_signal=shutdown_signal,
            input_queue=audio_output_queue,
            audio_chunk_queue=self._audio_chunk_queue,
            tts_engine=tts_engine,
        )
        self._playback_worker = PlaybackWorker(
            name="PlaybackThread",
            stop_signal=shutdown_signal,
            audio_chunk_queue=self._audio_chunk_queue,
        )

    @property
    def speaker(self) -> AudioOutput:
        """Access for interruption control (e.g. speaker.interrupt()). No-op for now."""
        return self

    def interrupt(self) -> None:
        """Interrupt current playback. Not implemented yet; no-op."""
        pass

    def start(self) -> None:
        """Start TTS and playback threads."""
        self._tts_worker.start()
        self._playback_worker.start()

    def join(self) -> None:
        """Wait for both threads to finish."""
        self._tts_worker.join()
        self._playback_worker.join()


__all__ = [
    "AudioOutput",
    "AudioOutputConfig",
    "AudioOutputRequest",
    "AudioChunk",
    "PlaybackWorker",
    "TTSWorker",
]
