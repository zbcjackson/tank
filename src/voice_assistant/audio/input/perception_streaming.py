"""Streaming Perception thread: Real-time ASR using Sherpa-ONNX."""

from __future__ import annotations

import logging
import queue
from typing import TYPE_CHECKING

from ...core.events import BrainInputEvent, DisplayMessage, InputType
from ...core.runtime import RuntimeContext
from ...core.shutdown import StopSignal
from ...core.worker import QueueWorker

if TYPE_CHECKING:
    from .asr_sherpa import SherpaASR
    from .mic import AudioFrame

logger = logging.getLogger("StreamingPerception")

class StreamingPerception(QueueWorker["AudioFrame"]):
    """
    Consumes AudioFrame directly from Mic and emits real-time BrainInputEvent/DisplayMessage.
    
    Uses SherpaASR for streaming recognition.
    """

    def __init__(
        self,
        shutdown_signal: StopSignal,
        runtime: RuntimeContext,
        frames_queue: "queue.Queue[AudioFrame]",
        asr: "SherpaASR",
        user: str = "User",
        on_speech_interrupt: Optional[Callable[[], None]] = None,
    ):
        super().__init__(
            name="StreamingPerceptionThread",
            stop_signal=shutdown_signal,
            input_queue=frames_queue,
            poll_interval_s=0.01, # Low poll interval for responsiveness
        )
        self._runtime = runtime
        self._asr = asr
        self._user = user
        self._on_speech_interrupt = on_speech_interrupt
        self._last_text = ""
        self._interrupt_fired_for_current = False

    def handle(self, frame: "AudioFrame") -> None:
        text, is_final = self._asr.process_pcm(frame.pcm)
        
        # Trigger interrupt as soon as any text is detected
        if text and not self._interrupt_fired_for_current:
            if self._on_speech_interrupt:
                logger.info("Speech detected, triggering interrupt")
                self._on_speech_interrupt()
            self._interrupt_fired_for_current = True

        # Only update if text has changed
        if text != self._last_text:
            self._last_text = text
            if text:
                # Push partial/final result to UI
                self._runtime.display_queue.put(DisplayMessage(
                    speaker=self._user, 
                    text=text, 
                    is_final=is_final
                ))
        
        if is_final:
            if text:
                logger.info("Final transcription: %s", text)
                # Push final result to Brain
                self._runtime.brain_input_queue.put(BrainInputEvent(
                    type=InputType.AUDIO,
                    text=text,
                    user=self._user,
                    language=None, # SherpaASR bilingual model handles this internally
                    confidence=None,
                ))
            self._last_text = "" # Reset for next utterance
            self._interrupt_fired_for_current = False
