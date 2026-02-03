"""TTS worker: AudioOutputRequest -> AudioChunk stream into a queue."""

from __future__ import annotations

import asyncio
import logging
import queue
from typing import TYPE_CHECKING

from ...core.events import AudioOutputRequest
from ...core.shutdown import StopSignal
from ...core.worker import QueueWorker
from .types import AudioChunk

if TYPE_CHECKING:
    from .tts import TTSEngine

logger = logging.getLogger("Speaker")


class TTSWorker(QueueWorker[AudioOutputRequest]):
    """
    Consumes AudioOutputRequest from queue, generates AudioChunk via TTS,
    puts chunks into audio_chunk_queue and None as end marker.
    """

    def __init__(
        self,
        *,
        name: str,
        stop_signal: StopSignal,
        input_queue: "queue.Queue[AudioOutputRequest]",
        audio_chunk_queue: "queue.Queue[AudioChunk | None]",
        tts_engine: "TTSEngine",
        poll_interval_s: float = 0.1,
    ):
        super().__init__(
            name=name,
            stop_signal=stop_signal,
            input_queue=input_queue,
            poll_interval_s=poll_interval_s,
        )
        self._audio_chunk_queue = audio_chunk_queue
        self._tts_engine = tts_engine

    def _setup_event_loop(self) -> asyncio.AbstractEventLoop:
        """Create event loop for TTS async operations."""
        return asyncio.new_event_loop()

    def run(self) -> None:
        logger.info("TTSWorker started")
        try:
            super().run()
        finally:
            logger.info("TTSWorker stopped")

    def handle(self, item: AudioOutputRequest) -> None:
        logger.info(
            "TTSWorker: got request content=%r language=%s",
            item.content[:50] if item.content else "",
            item.language,
        )

        async def generate_chunks() -> None:
            chunk_count = 0
            try:
                chunk_stream = self._tts_engine.generate_stream(
                    item.content,
                    language=item.language,
                    voice=item.voice,
                    is_interrupted=None,
                )
                logger.info("TTSWorker: starting generate_stream")
                async for chunk in chunk_stream:
                    self._audio_chunk_queue.put(chunk)
                    chunk_count += 1
                logger.info(
                    "TTSWorker: stream done, put %d chunks, sending end marker",
                    chunk_count,
                )
            except Exception as e:
                logger.exception("TTSWorker: generate_stream failed: %s", e)
                raise
            finally:
                self._audio_chunk_queue.put(None)

        assert self._loop is not None
        self._loop.run_until_complete(generate_chunks())
        logger.info(
            "TTSWorker: handle finished for content=%r",
            item.content[:50] if item.content else "",
        )

