"""Callback-based audio sink for capturing output."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional, Callable

from .types import AudioSink, AudioChunk
from ...core.shutdown import StopSignal

logger = logging.getLogger("CallbackSink")


class CallbackAudioSink:
    """
    An AudioSink that consumes chunks from a queue and passes them to a callback.
    Useful for capturing output in tests or sending via WebSocket.
    """

    def __init__(
        self,
        stop_signal: StopSignal,
        audio_chunk_queue: queue.Queue[AudioChunk | None],
        on_chunk: Callable[[AudioChunk], None],
        on_stream_end: Optional[Callable[[], None]] = None,
    ):
        self._stop_signal = stop_signal
        self._audio_chunk_queue = audio_chunk_queue
        self._on_chunk = on_chunk
        self._on_stream_end = on_stream_end
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the sink thread."""
        self._thread = threading.Thread(target=self._run, name="CallbackSinkThread", daemon=True)
        self._thread.start()
        logger.info("CallbackAudioSink started")

    def _run(self) -> None:
        while not self._stop_signal.is_set():
            try:
                chunk = self._audio_chunk_queue.get(timeout=0.1)
                if chunk is None:
                    if self._on_stream_end:
                        self._on_stream_end()
                    continue
                self._on_chunk(chunk)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in CallbackAudioSink: {e}")

    def join(self) -> None:
        """Wait for the thread to finish."""
        if self._thread:
            self._thread.join()
        logger.info("CallbackAudioSink joined")
