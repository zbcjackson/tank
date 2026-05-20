"""VADProcessor — wraps a VADStream as a pipeline Processor."""

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
    from ...audio.input.vad import VADStream

logger = logging.getLogger(__name__)


class EndOfUtterance:
    """Sentinel pushed into VAD's input queue to force-finalize speech.

    Handled exclusively by ``VADProcessor.process``: drained on VAD's own
    thread, after every in-flight audio frame, so concurrent access to
    ``VADStream`` state never races. Used by client-driven end-of-utterance
    signals (push-to-talk).
    """

    __slots__ = ()


END_OF_UTTERANCE = EndOfUtterance()


class VADProcessor(Processor):
    """Wraps a ``VADStream`` as a pipeline Processor.

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
        vad_stream: VADStream,
        bus: Bus | None = None,
        playback_threshold: float | None = None,
    ) -> None:
        super().__init__(name="vad")
        self.input_caps = AudioCaps(sample_rate=16000)
        self._vad = vad_stream
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

        # ── EndOfUtterance sentinel: force-finalize speech on VAD thread ──
        if isinstance(item, EndOfUtterance):
            result = self._vad.flush(time.time())
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
            else:
                yield FlowReturn.OK, None
            return

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

        elif result.status == VADStatus.START_SPEECH:
            self._speech_active = True
            # Forward START_SPEECH result so ASR can start session
            yield FlowReturn.OK, result

        elif result.status == VADStatus.IN_SPEECH:
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

    def flush_speech(self) -> Any | None:
        """Force-finalize in-progress speech and return the END_SPEECH ``VADResult``.

        Used by client-driven end-of-utterance signals (push-to-talk) where the
        speaker explicitly marks the end of an utterance instead of waiting
        for VAD silence detection. Returns ``None`` if no speech is in
        progress, in which case callers should treat it as a no-op.
        """
        from ...audio.input.vad import VADStatus

        result = self._vad.flush(time.time())
        if result.status != VADStatus.END_SPEECH:
            return None
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
        return result
