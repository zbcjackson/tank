"""Perception thread: ASR + voiceprint recognition."""

import threading
import time
import logging
import queue
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional
from dataclasses import dataclass

from .shutdown import GracefulShutdown
from .queues import brain_input_queue, BrainInputEvent, InputType

# Import Utterance from audio module
from voice_assistant.audio.segmenter import Utterance

logger = logging.getLogger("RefactoredAssistant")


@dataclass(frozen=True)
class PerceptionConfig:
    """Configuration for Perception thread."""
    enable_voiceprint: bool = True
    voiceprint_timeout_s: float = 0.5  # Timeout for voiceprint recognition
    default_user: str = "Unknown"  # Fallback user if voiceprint fails


class Perception(threading.Thread):
    """
    The Translator: Middleware between Audio and Brain.
    
    Responsibilities:
    - ASR (Automatic Speech Recognition) on Utterance
    - Voiceprint recognition (speaker identification) - parallel with ASR
    - Emit BrainInputEvent with text, language, user, confidence
    
    Uses internal thread pool to parallelize ASR and voiceprint recognition
    for lower latency.
    """

    def __init__(
        self,
        shutdown_signal: GracefulShutdown,
        utterance_queue: queue.Queue[Utterance],
        config: PerceptionConfig = PerceptionConfig(),
    ):
        super().__init__(name="PerceptionThread")
        self.shutdown_signal = shutdown_signal
        self._utterance_queue = utterance_queue
        self._config = config
        
        # Thread pool for parallel ASR + voiceprint execution
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="PerceptionWorker")

    def run(self):
        """Main perception loop."""
        logger.info("Perception started. Translating audio...")
        while not self.shutdown_signal.is_set():
            try:
                # Read Utterance from Audio subsystem
                if not self._utterance_queue.empty():
                    utterance = self._utterance_queue.get_nowait()
                    processed_input = self.process(utterance)
                    brain_input_queue.put(processed_input)
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
        
        Returns BrainInputEvent with recognized text and metadata.
        
        Strategy:
        - ASR is required and must complete
        - Voiceprint recognition runs in parallel but has timeout
        - If voiceprint fails/times out, falls back to default_user
        """
        # Submit both tasks in parallel
        asr_future = self._executor.submit(self._run_asr, utterance)
        
        voiceprint_future = None
        if self._config.enable_voiceprint:
            voiceprint_future = self._executor.submit(self._run_voiceprint, utterance)
        
        # Wait for ASR (required)
        try:
            text, language, confidence = asr_future.result()
        except Exception as e:
            logger.error(f"ASR failed: {e}")
            # Return empty event or handle error appropriately
            raise
        
        # Wait for voiceprint (optional, with timeout)
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
        """
        Run ASR on utterance.
        
        Returns: (text, language, confidence)
        """
        raise NotImplementedError("ASR not implemented in skeleton.")

    def _run_voiceprint(self, utterance: Utterance) -> str:
        """
        Run voiceprint recognition on utterance.
        
        Returns: user_id (speaker identifier)
        """
        raise NotImplementedError("Voiceprint recognition not implemented in skeleton.")
