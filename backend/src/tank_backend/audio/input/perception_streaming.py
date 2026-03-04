"""Streaming Perception thread: Real-time ASR using Sherpa-ONNX."""

from __future__ import annotations

import logging
import queue
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...core.events import BrainInputEvent, DisplayMessage, InputType
from ...core.runtime import RuntimeContext
from ...core.shutdown import StopSignal
from ...core.worker import QueueWorker

if TYPE_CHECKING:
    from .asr_sherpa import SherpaASR
    from .mic import AudioFrame
    from .voiceprint_streaming import StreamingVoiceprintRecognizer

logger = logging.getLogger("StreamingPerception")


class StreamingPerception(QueueWorker["AudioFrame"]):
    """
    Consumes AudioFrame directly from Mic and emits real-time BrainInputEvent/DisplayMessage.

    Uses SherpaASR for streaming recognition.
    Optionally identifies speaker via StreamingVoiceprintRecognizer.
    """

    def __init__(
        self,
        shutdown_signal: StopSignal,
        runtime: RuntimeContext,
        frames_queue: queue.Queue[AudioFrame],
        asr: SherpaASR,
        user: str = "User",
        on_speech_interrupt: Callable[[], None] | None = None,
        voiceprint: StreamingVoiceprintRecognizer | None = None,
    ):
        super().__init__(
            name="StreamingPerceptionThread",
            stop_signal=shutdown_signal,
            input_queue=frames_queue,
            poll_interval_s=0.01,  # Low poll interval for responsiveness
        )
        self._runtime = runtime
        self._asr = asr
        self._user = user
        self._on_speech_interrupt = on_speech_interrupt
        self._voiceprint = voiceprint
        self._last_text = ""
        self._interrupt_fired_for_current = False
        self._current_msg_id: str | None = None

    def handle(self, frame: AudioFrame) -> None:
        # Accumulate audio for voiceprint identification
        if self._voiceprint:
            self._voiceprint.accumulate(frame)

        text, is_final = self._asr.process_pcm(frame.pcm)

        # Trigger interrupt as soon as any text is detected
        if text and not self._interrupt_fired_for_current:
            if self._on_speech_interrupt:
                logger.info("Speech detected, triggering interrupt")
                self._on_speech_interrupt()
            self._interrupt_fired_for_current = True

        # Identify speaker when utterance is complete
        speaker = self._user
        if is_final and self._voiceprint:
            speaker = self._voiceprint.identify_and_reset()

        # Only update if text has changed OR it's the final result
        if text != self._last_text or (is_final and text):
            self._last_text = text
            if text:
                if self._current_msg_id is None:
                    self._current_msg_id = f"user_{uuid.uuid4().hex[:8]}"

                # Push partial/final result to UI
                self._runtime.ui_queue.put(
                    DisplayMessage(
                        speaker=speaker if is_final else self._user,
                        text=text,
                        is_user=True,
                        is_final=is_final,
                        msg_id=self._current_msg_id,
                    )
                )

        if is_final:
            if text:
                logger.info("Final transcription: %s (speaker=%s)", text, speaker)
                # Push final result to Brain
                self._runtime.brain_input_queue.put(
                    BrainInputEvent(
                        type=InputType.AUDIO,
                        text=text,
                        user=speaker,
                        language="zh",
                        confidence=None,
                        metadata={"msg_id": self._current_msg_id},
                    )
                )
            else:
                # No text but is_final — reset voiceprint buffer
                if self._voiceprint:
                    self._voiceprint.identify_and_reset()
            self._last_text = ""  # Reset for next utterance
            self._interrupt_fired_for_current = False
            self._current_msg_id = None  # Reset ID for next utterance
