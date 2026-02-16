"""Queue-based audio source for virtual/remote audio input."""

from __future__ import annotations

import queue
import logging
import threading
import time
from typing import Optional

from .types import AudioSource, AudioFrame

logger = logging.getLogger("QueueSource")


class QueueAudioSource:
    """
    An AudioSource that consumes frames from an internal queue.
    Useful for receiving audio via WebSocket or tests.
    """

    def __init__(
        self,
        frames_queue: queue.Queue[AudioFrame],
    ):
        self._frames_queue = frames_queue
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """
        In this implementation, start doesn't need to do much as the 
        actual 'pushing' into the queue happens externally. 
        But we might want a thread to monitor or manage the source.
        For now, we just satisfy the interface.
        """
        logger.info("QueueAudioSource started")

    def join(self) -> None:
        """Satisfy the interface."""
        logger.info("QueueAudioSource joined")

    def push(self, frame: AudioFrame) -> None:
        """External API to push frames into this source."""
        try:
            self._frames_queue.put_nowait(frame)
        except queue.Full:
            logger.warning("QueueAudioSource: internal queue full, dropping frame")

    def stop(self) -> None:
        """Stop the source."""
        self._stop_event.set()
