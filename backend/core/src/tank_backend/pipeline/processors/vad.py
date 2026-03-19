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
    Output: AudioFrame (during speech) or VADResult (END_SPEECH with utterance PCM)

    Forwards AudioFrame downstream during speech so ASR can do streaming
    recognition.  The ASR processor is responsible for posting speech_start
    to the bus once it produces a non-empty partial transcript.

    Posts speech timing metrics to Bus.

    During TTS playback, raises the VAD threshold to filter out echo
    from speakers (Layer 1 of echo guard).
    """

    def __init__(
        self,
        vad: SileroVAD,
        bus: Bus | None = None,
        playback_threshold: float | None = None,
    ) -> None:
        super().__init__(name="vad")
        self.input_caps = AudioCaps(sample_rate=16000)
        self._vad = vad
        self._bus = bus
        self._speech_active = False
        self._playback_threshold = playback_threshold

        # Subscribe to playback state for dynamic threshold adjustment
        if self._bus and self._playback_threshold is not None:
            self._bus.subscribe("playback_started", self._on_playback_started)
            self._bus.subscribe("playback_ended", self._on_playback_ended)

    def _on_playback_started(self, _message: BusMessage) -> None:
        if self._playback_threshold is not None:
            self._vad.set_threshold(self._playback_threshold)

    def _on_playback_ended(self, _message: BusMessage) -> None:
        self._vad.reset_threshold()

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        from ...audio.input.vad import VADStatus

        frame: AudioFrame = item
        result = self._vad.process_frame(frame.pcm, frame.timestamp_s)

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
            self._speech_active = True
            # Forward the AudioFrame so downstream ASR can do streaming recognition
            yield FlowReturn.OK, frame

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
