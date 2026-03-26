"""ASRProcessor — wraps streaming ASR as a pipeline Processor."""

from __future__ import annotations

import contextlib
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

    Input:
      - VADResult(START_SPEECH) — start ASR session
      - AudioFrame — process audio, get partial transcripts
      - VADResult(END_SPEECH) — stop ASR session, get final transcript

    Output:
      - BrainInputEvent (on END_SPEECH with non-empty text)

    Bus messages posted:
      - speech_start — when speech starts (triggers assistant interrupt)
      - ui_message — partial and final transcripts for UI
      - asr_result — transcription metrics

    For non-streaming engines (supports_streaming=False):
      - AudioFrame → ignored
      - VADResult END_SPEECH → batch transcribe full utterance PCM
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
        self._streaming_msg_id: str | None = None
        self._streaming_started_at: float | None = None

    def _reset_state(self) -> None:
        """Reset state for a new utterance."""
        self._partial_text = ""
        self._streaming_msg_id = None
        self._streaming_started_at = None

    def _post_speech_start(self, timestamp_s: float | None = None) -> None:
        """Post speech_start to bus (triggers interrupt in assistant)."""
        if self._bus:
            self._bus.post(BusMessage(
                type="speech_start",
                source=self.name,
                payload={"timestamp_s": timestamp_s},
            ))

    def _post_partial(self, text: str) -> None:
        """Post partial transcript to UI."""
        if self._bus and self._streaming_msg_id:
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=self._make_display_message(text, is_final=False),
            ))

    def _post_final(self, text: str) -> None:
        """Post final transcript to UI."""
        if self._bus and self._streaming_msg_id:
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=self._make_display_message(text, is_final=True),
            ))

    def _make_display_message(self, text: str, is_final: bool) -> Any:
        """Create a DisplayMessage for UI."""
        from ...core.events import DisplayMessage
        return DisplayMessage(
            speaker=self._user,
            text=text,
            is_user=True,
            is_final=is_final,
            msg_id=self._streaming_msg_id,
        )

    def _post_metrics(
        self,
        text: str,
        elapsed: float,
        started_at_s: float | None,
        ended_at_s: float | None,
    ) -> None:
        """Post ASR metrics to bus."""
        if self._bus:
            self._bus.post(BusMessage(
                type="asr_result",
                source=self.name,
                payload={
                    "text": text,
                    "is_final": True,
                    "latency_s": elapsed,
                    "audio_duration_s": (
                        (ended_at_s - started_at_s)
                        if started_at_s and ended_at_s
                        else None
                    ),
                },
            ))

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        from ...audio.input.types import AudioFrame
        from ...audio.input.vad import VADResult, VADStatus
        from ...core.events import BrainInputEvent, InputType

        # ── START_SPEECH: begin ASR session ──────────────────────────────
        if isinstance(item, VADResult) and item.status == VADStatus.START_SPEECH:
            self._asr.start()
            self._streaming_msg_id = f"user_{uuid.uuid4().hex[:8]}"
            self._streaming_started_at = time.time()
            self._post_speech_start(item.started_at_s)
            logger.debug("ASR session started")
            yield FlowReturn.OK, None
            return

        # ── AudioFrame: streaming recognition ────────────────────────────
        if isinstance(item, AudioFrame):
            if not self._asr.supports_streaming:
                yield FlowReturn.OK, None
                return

            text = self._asr.process_pcm(item.pcm)

            if text and text != self._partial_text:
                self._partial_text = text
                self._post_partial(text)

            yield FlowReturn.OK, None
            return

        # ── END_SPEECH: finalize utterance ───────────────────────────────
        if isinstance(item, VADResult) and item.status == VADStatus.END_SPEECH:
            if item.utterance_pcm is None or len(item.utterance_pcm) == 0:
                self._reset_state()
                yield FlowReturn.OK, None
                return

            # Get final transcript
            if self._asr.supports_streaming:
                final_text = self._asr.stop()
                if not final_text:
                    final_text = self._partial_text
                elapsed = (
                    time.time() - self._streaming_started_at
                    if self._streaming_started_at
                    else 0.0
                )
            else:
                # Batch mode: transcribe full utterance
                started_at = time.time()
                self._asr.start()
                self._asr.process_pcm(item.utterance_pcm)
                final_text = self._asr.stop()
                elapsed = time.time() - started_at
                # For batch mode, create msg_id and post speech_start now
                self._streaming_msg_id = f"user_{uuid.uuid4().hex[:8]}"
                if final_text:
                    self._post_speech_start()

            # Post metrics
            self._post_metrics(final_text, elapsed, item.started_at_s, item.ended_at_s)

            if final_text:
                self._post_final(final_text)

                msg_id = self._streaming_msg_id or f"user_{uuid.uuid4().hex[:8]}"
                utterance_id = (
                    f"{item.started_at_s:.3f}_{item.ended_at_s:.3f}"
                    if item.started_at_s is not None and item.ended_at_s is not None
                    else msg_id
                )

                event = BrainInputEvent(
                    type=InputType.AUDIO,
                    text=final_text,
                    user=self._user,
                    language="zh",
                    confidence=None,
                    metadata={"msg_id": msg_id, "utterance_id": utterance_id},
                )
                self._reset_state()
                yield FlowReturn.OK, event
            else:
                self._reset_state()
                yield FlowReturn.OK, None
            return

        # Unsupported input type
        yield FlowReturn.OK, None

    def handle_event(self, event: PipelineEvent) -> bool:
        if event.type == "flush":
            with contextlib.suppress(Exception):
                self._asr.stop()  # Discard any partial results
            self._reset_state()
            return False  # propagate
        return False
