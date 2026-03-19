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

    Input: VADResult (END_SPEECH with utterance PCM) or AudioFrame (streaming)
    Output: BrainInputEvent (final transcription)

    For streaming engines (supports_streaming=True):
      - AudioFrame → feed to ASR, post partial transcripts, post speech_start
        on first non-empty partial.  Yield None (brain waits for final).
      - VADResult END_SPEECH → finalize with accumulated partial text, yield
        BrainInputEvent.

    For non-streaming engines (supports_streaming=False):
      - AudioFrame → ignored (yield None)
      - VADResult END_SPEECH → batch transcribe full utterance PCM, post
        speech_start + final transcript, yield BrainInputEvent.

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

        # Streaming state
        self._partial_text: str = ""
        self._speech_start_posted: bool = False
        self._streaming_msg_id: str | None = None
        self._streaming_started_at: float | None = None

    def _reset_streaming_state(self) -> None:
        """Reset streaming state for a new utterance."""
        self._partial_text = ""
        self._speech_start_posted = False
        self._streaming_msg_id = None
        self._streaming_started_at = None

    def _post_speech_start(self, timestamp_s: float | None = None) -> None:
        """Post speech_start to bus (triggers interrupt in assistant)."""
        if self._bus and not self._speech_start_posted:
            self._speech_start_posted = True
            self._bus.post(BusMessage(
                type="speech_start",
                source=self.name,
                payload={"timestamp_s": timestamp_s},
            ))

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        from ...audio.input.types import AudioFrame
        from ...audio.input.vad import VADResult, VADStatus
        from ...core.events import BrainInputEvent, DisplayMessage, InputType

        # ── AudioFrame: streaming recognition ────────────────────────────
        if isinstance(item, AudioFrame):
            if not self._asr.supports_streaming:
                yield FlowReturn.OK, None
                return

            if self._streaming_started_at is None:
                self._streaming_started_at = time.time()

            if self._streaming_msg_id is None:
                self._streaming_msg_id = f"user_{uuid.uuid4().hex[:8]}"

            text, is_endpoint = self._asr.process_pcm(item.pcm)

            if text and text != self._partial_text:
                self._partial_text = text

                # First non-empty partial → trigger interrupt
                self._post_speech_start(item.timestamp_s)

                # Post partial transcript to UI
                if self._bus:
                    self._bus.post(BusMessage(
                        type="ui_message",
                        source=self.name,
                        payload=DisplayMessage(
                            speaker=self._user,
                            text=text,
                            is_user=True,
                            is_final=False,
                            msg_id=self._streaming_msg_id,
                        ),
                    ))

            # If Sherpa detected an endpoint mid-stream, capture the text
            # before it auto-resets.  We don't finalize yet — wait for
            # VAD END_SPEECH to produce the BrainInputEvent.
            if is_endpoint and text:
                self._partial_text = text

            yield FlowReturn.OK, None
            return

        # ── VADResult END_SPEECH: finalize utterance ─────────────────────
        if isinstance(item, VADResult):
            if item.status != VADStatus.END_SPEECH:
                yield FlowReturn.OK, None
                return

            if item.utterance_pcm is None or len(item.utterance_pcm) == 0:
                self._reset_streaming_state()
                yield FlowReturn.OK, None
                return

            # Determine final text
            if self._asr.supports_streaming and self._partial_text:
                # Use accumulated streaming text
                final_text = self._partial_text
                elapsed = (
                    time.time() - self._streaming_started_at
                    if self._streaming_started_at
                    else 0.0
                )
            else:
                # Batch mode: transcribe the full utterance now
                started_at = time.time()
                final_text, _ = self._asr.process_pcm(item.utterance_pcm)
                elapsed = time.time() - started_at

                # For non-streaming engines, post speech_start now
                # so the assistant can interrupt if needed
                if final_text and not self._asr.supports_streaming:
                    self._post_speech_start()

            msg_id = self._streaming_msg_id or f"user_{uuid.uuid4().hex[:8]}"

            # Post ASR metrics
            if self._bus:
                self._bus.post(BusMessage(
                    type="asr_result",
                    source=self.name,
                    payload={
                        "text": final_text,
                        "is_final": True,
                        "latency_s": elapsed,
                        "audio_duration_s": (
                            (item.ended_at_s - item.started_at_s)
                            if item.started_at_s and item.ended_at_s
                            else None
                        ),
                    },
                ))

            if final_text:
                utterance_id = (
                    f"{item.started_at_s:.3f}_{item.ended_at_s:.3f}"
                    if item.started_at_s is not None and item.ended_at_s is not None
                    else msg_id
                )

                # Post final user transcript to UI
                if self._bus:
                    self._bus.post(BusMessage(
                        type="ui_message",
                        source=self.name,
                        payload=DisplayMessage(
                            speaker=self._user,
                            text=final_text,
                            is_user=True,
                            is_final=True,
                            msg_id=msg_id,
                        ),
                    ))

                event = BrainInputEvent(
                    type=InputType.AUDIO,
                    text=final_text,
                    user=self._user,
                    language="zh",
                    confidence=None,
                    metadata={"msg_id": msg_id, "utterance_id": utterance_id},
                )
                self._reset_streaming_state()
                self._asr.reset()
                yield FlowReturn.OK, event
            else:
                self._reset_streaming_state()
                self._asr.reset()
                yield FlowReturn.OK, None
            return

        # Unsupported input type
        yield FlowReturn.OK, None

    def handle_event(self, event: PipelineEvent) -> bool:
        if event.type == "flush":
            self._reset_streaming_state()
            if hasattr(self._asr, "reset"):
                self._asr.reset()
            return False  # propagate
        return False
