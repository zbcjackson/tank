"""Speaker thread consuming audio output queue."""

from __future__ import annotations

import threading
import time
import logging
import queue

from ...core.shutdown import GracefulShutdown
from ...core.worker import QueueWorker

logger = logging.getLogger("RefactoredAssistant")


class SpeakerHandler(QueueWorker[dict]):
    """
    The Mouth: Continuously checks AudioOutputQueue and plays audio.
    Supports interruption.
    """

    def __init__(self, shutdown_signal: GracefulShutdown, audio_output_queue: "queue.Queue[dict]"):
        super().__init__(
            name="SpeakerThread",
            stop_signal=shutdown_signal,
            input_queue=audio_output_queue,
            poll_interval_s=0.5,
        )
        self.interrupt_event = threading.Event()

    def interrupt(self):
        """Signal to stop current playback immediately."""
        self.interrupt_event.set()
        # Also clear the queue of pending audio to fully reset
        with self._input_queue.mutex:
            self._input_queue.queue.clear()
        logger.warning("🚫 Speaker Interrupted!")

    def run(self) -> None:
        logger.info("SpeakerHandler started. Waiting for audio...")
        try:
            super().run()
        finally:
            logger.info("SpeakerHandler stopped.")

    def handle(self, item: dict) -> None:
        text_to_speak = item.get("content", "")
        logger.info(f"🔊 Starting playback: '{text_to_speak}'")

        # Simulate playback chunk by chunk to allow interruption
        # Assume roughly 0.1s per character for simulation
        duration = len(text_to_speak) * 0.1
        chunks = int(duration / 0.1)

        self.interrupt_event.clear()  # Reset interrupt flag

        for _ in range(chunks):
            if self._stop_signal.is_set() or self.interrupt_event.is_set():
                logger.info("Playback stopped early.")
                break
            time.sleep(0.1)

        if not self.interrupt_event.is_set():
            logger.info("✅ Playback finished.")
