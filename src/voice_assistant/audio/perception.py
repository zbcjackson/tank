"""Perception thread: ASR + voiceprint recognition for utterances."""

from __future__ import annotations

import threading
import time
import logging
import queue
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Optional

from voice_assistant.core.shutdown import GracefulShutdown
from voice_assistant.core.queues import BrainInputEvent, InputType
from voice_assistant.core.runtime import RuntimeContext

from .segmenter import Utterance

logger = logging.getLogger("RefactoredAssistant")


@dataclass(frozen=True)
class PerceptionConfig:
    """Configuration for Perception thread."""

    enable_voiceprint: bool = True
    voiceprint_timeout_s: float = 0.5
    default_user: str = "Unknown"


class Perception(threading.Thread):
    """
    Consumes Utterance from Audio subsystem and emits BrainInputEvent into runtime.

    Parallelizes ASR and voiceprint recognition for lower latency.
    """

    def __init__(
        self,
        shutdown_signal: GracefulShutdown,
        runtime: RuntimeContext,
        utterance_queue: "queue.Queue[Utterance]",
        config: PerceptionConfig = PerceptionConfig(),
    ):
        super().__init__(name="PerceptionThread")
        self.shutdown_signal = shutdown_signal
        self._runtime = runtime
        self._utterance_queue = utterance_queue
        self._config = config

        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="PerceptionWorker")

    def run(self):
        logger.info("Perception started. Translating audio...")
        while not self.shutdown_signal.is_set():
            try:
                if not self._utterance_queue.empty():
                    utterance = self._utterance_queue.get_nowait()
                    event = self.process(utterance)
                    self._runtime.brain_input_queue.put(event)
                    self._utterance_queue.task_done()
                    continue
            except queue.Empty:
                pass

            time.sleep(0.1)

        logger.info("Perception stopped.")
        self._executor.shutdown(wait=True)

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
        raise NotImplementedError("ASR not implemented in skeleton.")

    def _run_voiceprint(self, utterance: Utterance) -> str:
        raise NotImplementedError("Voiceprint recognition not implemented in skeleton.")

