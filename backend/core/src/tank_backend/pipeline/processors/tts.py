"""TTSProcessor — wraps TTS engine as a pipeline Processor."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import FlowReturn, Processor
from .tts_normalizer import normalize_for_tts

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
    Posts QoS feedback when overloaded.
    """

    QOS_QUEUE_FILL_THRESHOLD = 0.80  # 80% full
    QOS_CONSECUTIVE_THRESHOLD = 3  # need N consecutive overloaded items

    def __init__(self, tts_engine: TTSEngine, bus: Bus | None = None) -> None:
        super().__init__(name="tts")
        self._tts_engine = tts_engine
        self._bus = bus
        self._interrupted = False
        self._qos_overload_count = 0
        self._feeding_queue: Any = None  # set by assistant after pipeline build

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        request: AudioOutputRequest = item
        self._interrupted = False

        # QoS: check if feeding queue is overloaded
        self._check_qos()

        # Normalize text for speech (strip markdown, emoji, special chars)
        normalized_text = normalize_for_tts(request.content)
        if not normalized_text.strip():
            logger.info("TTSProcessor: nothing speakable after normalization, skipping")
            return

        logger.info(
            "TTSProcessor: received AudioOutputRequest"
            f" (original_len={len(request.content)}, normalized_len={len(normalized_text)},"
            f" lang={request.language})"
        )

        started_at = time.time()
        chunk_count = 0

        chunk_stream = self._tts_engine.generate_stream(
            normalized_text,
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
        except Exception as e:
            logger.warning("TTSProcessor: TTS engine error after %d chunks: %s", chunk_count, e)
        finally:
            await chunk_stream.aclose()
            logger.info("TTSProcessor: finished, yielded %d chunks", chunk_count)

        elapsed = time.time() - started_at

        if self._bus:
            self._bus.post(BusMessage(
                type="tts_finished",
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

    def _check_qos(self) -> None:
        """Post QoS feedback to bus when feeding queue is overloaded."""
        if self._feeding_queue is None or self._bus is None:
            return

        fill_pct = self._feeding_queue.qsize / max(self._feeding_queue._queue.maxsize, 1)
        if fill_pct >= self.QOS_QUEUE_FILL_THRESHOLD:
            self._qos_overload_count += 1
        else:
            self._qos_overload_count = 0

        if self._qos_overload_count >= self.QOS_CONSECUTIVE_THRESHOLD:
            severity = min(fill_pct, 1.0)
            self._bus.post(BusMessage(
                type="qos",
                source=self.name,
                payload={"severity": severity, "fill_pct": fill_pct},
            ))
            logger.warning(
                "TTS QoS: queue %.0f%% full (severity=%.2f)", fill_pct * 100, severity
            )
            self._qos_overload_count = 0  # Reset after posting
