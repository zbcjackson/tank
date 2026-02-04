"""Perception thread: ASR + voiceprint recognition for utterances."""

from __future__ import annotations

import logging
import queue
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from ...core.events import BrainInputEvent, DisplayMessage, InputType
from ...core.runtime import RuntimeContext
from ...core.shutdown import StopSignal
from ...core.worker import QueueWorker

from .segmenter import Utterance
from .voiceprint import VoiceprintRecognizer

if TYPE_CHECKING:
    from .asr import ASR

logger = logging.getLogger("Perception")


@dataclass(frozen=True)
class PerceptionConfig:
    """Configuration for Perception thread."""

    enable_voiceprint: bool = True
    voiceprint_timeout_s: float = 0.5
    default_user: str = "Unknown"
    model_size: str = "large-v3"


class Perception(QueueWorker[Utterance]):
    """
    Consumes Utterance from Audio subsystem and emits BrainInputEvent into runtime.

    Parallelizes ASR and voiceprint recognition for lower latency.
    """

    def __init__(
        self,
        shutdown_signal: StopSignal,
        runtime: RuntimeContext,
        utterance_queue: "queue.Queue[Utterance]",
        asr: "ASR",
        voiceprint: VoiceprintRecognizer,
        config: PerceptionConfig = PerceptionConfig(),
    ):
        super().__init__(
            name="PerceptionThread",
            stop_signal=shutdown_signal,
            input_queue=utterance_queue,
            poll_interval_s=0.1,
        )
        self._runtime = runtime
        self._config = config
        self._asr = asr
        self._voiceprint = voiceprint

        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="PerceptionWorker")

    def run(self) -> None:
        logger.info("Perception started. Translating audio...")
        try:
            super().run()
        finally:
            logger.info("Perception stopped.")
            self._executor.shutdown(wait=True)

    def handle(self, utterance: Utterance) -> None:
        event = self.process(utterance)
        # Skip blank text: don't put into brain_input_queue or display_queue
        if not event.text or not event.text.strip():
            return

        self._runtime.display_queue.put(DisplayMessage(speaker=event.user, text=event.text))
        self._runtime.brain_input_queue.put(event)

    def process(self, utterance: Utterance) -> BrainInputEvent:
        """
        Process Utterance: ASR + voiceprint recognition (parallel execution).

        Strategy:
        - ASR is required and must complete
        - Voiceprint recognition runs in parallel but has timeout
        - If voiceprint fails/times out, falls back to default_user
        """
        asr_future = self._executor.submit(self._run_asr, utterance)

        voiceprint_future = None
        if self._config.enable_voiceprint:
            voiceprint_future = self._executor.submit(self._run_voiceprint, utterance)

        text, language, confidence = asr_future.result()

        user = self._config.default_user
        if voiceprint_future is not None:
            try:
                user = voiceprint_future.result(timeout=self._config.voiceprint_timeout_s)
            except FutureTimeoutError:
                logger.warning("Voiceprint recognition timed out, using default user")
            except Exception as e:
                logger.warning(f"Voiceprint recognition failed: {e}, using default user")

        return BrainInputEvent(
            type=InputType.AUDIO,
            text=text,
            user=user,
            language=language,
            confidence=confidence,
        )

    def _run_asr(self, utterance: Utterance) -> tuple[str, Optional[str], Optional[float]]:
        return self._asr.transcribe(utterance.pcm, utterance.sample_rate)

    def _run_voiceprint(self, utterance: Utterance) -> str:
        return self._voiceprint.identify(utterance)
