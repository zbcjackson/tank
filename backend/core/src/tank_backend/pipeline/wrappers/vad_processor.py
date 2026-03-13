"""VADProcessor — wraps SileroVAD as a pipeline Processor."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import AudioCaps, FlowReturn, Processor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ...audio.input.types import AudioFrame
    from ...audio.input.vad import SileroVAD

logger = logging.getLogger(__name__)


class VADProcessor(Processor):
    """Wraps SileroVAD as a pipeline Processor.

    Input: AudioFrame (float32, 16 kHz)
    Output: VADResult (only END_SPEECH results with utterance PCM)

    Emits interrupt event upstream on first speech detection.
    Posts speech timing metrics to Bus.
    """

    def __init__(self, vad: SileroVAD, bus: Bus | None = None) -> None:
        super().__init__(name="vad")
        self.input_caps = AudioCaps(sample_rate=16000)
        self._vad = vad
        self._bus = bus
        self._speech_active = False

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        from ...audio.input.vad import VADStatus

        frame: AudioFrame = item
        result = self._vad.process_frame(frame.pcm, frame.timestamp_s)

        if result.status == VADStatus.IN_SPEECH and not self._speech_active:
            self._speech_active = True
            if self._bus:
                self._bus.post(BusMessage(
                    type="speech_start",
                    source=self.name,
                    payload={"timestamp_s": frame.timestamp_s},
                ))

        if result.status == VADStatus.END_SPEECH:
            self._speech_active = False
            if self._bus:
                self._bus.post(BusMessage(
                    type="speech_end",
                    source=self.name,
                    payload={
                        "started_at_s": result.started_at_s,
                        "ended_at_s": result.ended_at_s,
                    },
                ))
            yield FlowReturn.OK, result

        elif result.status == VADStatus.IN_SPEECH:
            # Accumulating — no output yet
            yield FlowReturn.OK, None

        else:
            # NO_SPEECH — pass through silently
            yield FlowReturn.OK, None

    def handle_event(self, event: PipelineEvent) -> bool:
        if event.type == "flush":
            now_s = time.time()
            self._vad.flush(now_s)
            self._speech_active = False
            return False  # propagate
        return False
