"""Client-side audio playback: WebSocket audio -> sounddevice."""

from __future__ import annotations

import contextlib
import logging
import queue
import threading

from ..audio.frame import decode_audio_frame
from ..audio.output.playback_worker import PlaybackWorker
from ..audio.output.types import AudioChunk
from ..core.shutdown import GracefulShutdown

logger = logging.getLogger("AudioPlayback")


class ClientAudioPlayback:
    """
    Receives audio bytes from WebSocket and plays via PlaybackWorker.

    Reuses the existing PlaybackWorker for sounddevice output.
    """

    def __init__(self, shutdown: GracefulShutdown):
        self._shutdown = shutdown
        self._chunk_queue: queue.Queue[AudioChunk | None] = queue.Queue(maxsize=50)
        self._interrupt_event = threading.Event()
        self._playback = PlaybackWorker(
            name="ClientPlaybackThread",
            stop_signal=shutdown,
            audio_chunk_queue=self._chunk_queue,
            interrupt_event=self._interrupt_event,
        )

    def start(self) -> None:
        """Start the PlaybackWorker thread."""
        self._playback.start()

    def on_audio_chunk(self, data: bytes) -> None:
        """Callback for TankClient — called when binary audio arrives from WS.

        Data is a framed audio buffer (header + Int16 PCM). The header carries
        the sample rate and channels chosen by the current TTS engine.
        """
        try:
            pcm, sample_rate, channels = decode_audio_frame(data)
        except ValueError as e:
            logger.warning("Dropping malformed audio frame: %s", e)
            return

        chunk = AudioChunk(data=pcm, sample_rate=sample_rate, channels=channels)
        try:
            self._chunk_queue.put_nowait(chunk)
        except queue.Full:
            logger.warning("Playback queue full, dropping chunk")

    def end_stream(self) -> None:
        """Signal end of current audio stream (push None marker)."""
        with contextlib.suppress(queue.Full):
            self._chunk_queue.put_nowait(None)

    def interrupt(self) -> None:
        """Interrupt current playback."""
        self._interrupt_event.set()
        with self._chunk_queue.mutex:
            self._chunk_queue.queue.clear()

    def stop(self) -> None:
        """Stop playback and wait for thread."""
        self._playback.join(timeout=2)
