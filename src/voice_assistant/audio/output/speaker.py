"""Speaker thread consuming audio output queue."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import TYPE_CHECKING

from ...core.events import AudioOutputRequest
from ...core.shutdown import StopSignal
from ...core.worker import QueueWorker
from .playback import play_stream

if TYPE_CHECKING:
    from .tts import TTSEngine

logger = logging.getLogger("Speaker")


class SpeakerHandler(QueueWorker[AudioOutputRequest]):
    """
    The Mouth: Consumes AudioOutputRequest from queue, runs TTS and playback.
    Supports interruption.
    """

    def __init__(
        self,
        shutdown_signal: StopSignal,
        audio_output_queue: "queue.Queue[AudioOutputRequest]",
        tts_engine: "TTSEngine",
    ):
        super().__init__(
            name="SpeakerThread",
            stop_signal=shutdown_signal,
            input_queue=audio_output_queue,
            poll_interval_s=0.5,
        )
        self._tts_engine = tts_engine
        self.interrupt_event = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    def interrupt(self) -> None:
        """Signal to stop current playback immediately."""
        self.interrupt_event.set()
        with self._input_queue.mutex:
            self._input_queue.queue.clear()
        logger.warning("🚫 Speaker Interrupted!")

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            logger.info("SpeakerHandler started. Waiting for audio...")
            super().run()
        finally:
            logger.info("SpeakerHandler stopped.")
            if self._loop:
                self._loop.close()

    def handle(self, item: AudioOutputRequest) -> None:
        self.interrupt_event.clear()

        async def do_speak() -> None:
            chunk_stream = self._tts_engine.generate_stream(
                item.content,
                language=item.language,
                voice=item.voice,
                is_interrupted=lambda: self.interrupt_event.is_set(),
            )
            await play_stream(
                chunk_stream,
                is_interrupted=lambda: self.interrupt_event.is_set(),
            )

        self._loop.run_until_complete(do_speak())
