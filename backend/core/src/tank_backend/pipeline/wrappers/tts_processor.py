"""TTSProcessor — wraps TTS engine as a pipeline Processor."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import FlowReturn, Processor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ...audio.output.tts import TTSEngine
    from ...core.events import AudioOutputRequest

logger = logging.getLogger(__name__)


class TTSProcessor(Processor):
    """Wraps a TTSEngine as a pipeline Processor.

    Input: AudioOutputRequest (text to speak)
    Output: AudioChunk (PCM audio chunks)

    Handles interrupt and flush events.
    Posts TTS latency metrics to Bus.
    """

    def __init__(self, tts_engine: TTSEngine, bus: Bus | None = None) -> None:
        super().__init__(name="tts")
        self._tts_engine = tts_engine
        self._bus = bus
        self._interrupted = False

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        request: AudioOutputRequest = item
        self._interrupted = False

        logger.info(f"TTSProcessor: received AudioOutputRequest (text_len={len(request.content)}, lang={request.language})")

        started_at = time.time()
        chunk_count = 0

        chunk_stream = self._tts_engine.generate_stream(
            request.content,
            language=request.language,
            voice=request.voice,
            is_interrupted=lambda: self._interrupted,
        )

        try:
            async for chunk in chunk_stream:
                if self._interrupted:
                    logger.info("TTSProcessor: interrupted after %d chunks", chunk_count)
                    break
                chunk_count += 1
                yield FlowReturn.OK, chunk
        finally:
            await chunk_stream.aclose()
            logger.info(f"TTSProcessor: finished, yielded {chunk_count} chunks")

        elapsed = time.time() - started_at

        if self._bus:
            self._bus.post(BusMessage(
                type="tts_latency",
                source=self.name,
                payload={
                    "latency_s": elapsed,
                    "chunk_count": chunk_count,
                    "interrupted": self._interrupted,
                    "text_length": len(request.content),
                },
            ))

    def handle_event(self, event: PipelineEvent) -> bool:
        if event.type == "interrupt":
            self._interrupted = True
            return False  # propagate
        if event.type == "flush":
            self._interrupted = True
            return False  # propagate
        return False
