"""ASRProcessor — wraps streaming ASR as a pipeline Processor."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import FlowReturn, Processor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tank_contracts import StreamingASREngine


logger = logging.getLogger(__name__)


class ASRProcessor(Processor):
    """Wraps a StreamingASREngine as a pipeline Processor.

    Input: VADResult (END_SPEECH with utterance PCM) or AudioFrame
    Output: BrainInputEvent (final transcription)

    Posts transcription metrics to Bus.
    """

    def __init__(
        self,
        asr: StreamingASREngine,
        bus: Bus | None = None,
        user: str = "User",
    ) -> None:
        super().__init__(name="asr")
        self._asr = asr
        self._bus = bus
        self._user = user

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        from ...audio.input.vad import VADResult
        from ...core.events import BrainInputEvent, InputType

        if isinstance(item, VADResult):
            if item.utterance_pcm is None or len(item.utterance_pcm) == 0:
                yield FlowReturn.OK, None
                return

            started_at = time.time()
            text, is_final = self._asr.process_pcm(item.utterance_pcm)
            elapsed = time.time() - started_at

            if self._bus:
                self._bus.post(BusMessage(
                    type="asr_result",
                    source=self.name,
                    payload={
                        "text": text,
                        "is_final": is_final,
                        "latency_s": elapsed,
                        "audio_duration_s": (
                            (item.ended_at_s - item.started_at_s)
                            if item.started_at_s and item.ended_at_s
                            else None
                        ),
                    },
                ))

            if text:
                msg_id = f"user_{uuid.uuid4().hex[:8]}"
                event = BrainInputEvent(
                    type=InputType.AUDIO,
                    text=text,
                    user=self._user,
                    language="zh",
                    confidence=None,
                    metadata={"msg_id": msg_id},
                )
                yield FlowReturn.OK, event
            else:
                yield FlowReturn.OK, None
        else:
            # Unsupported input type
            yield FlowReturn.OK, None

    def handle_event(self, event: PipelineEvent) -> bool:
        if event.type == "flush":
            # Reset ASR state if the engine supports it
            if hasattr(self._asr, "reset"):
                self._asr.reset()
            return False  # propagate
        return False
