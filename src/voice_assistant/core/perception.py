import threading
import time
import logging
import queue
from .shutdown import GracefulShutdown
from .queues import audio_input_queue, brain_input_queue, BrainInputEvent, InputType

logger = logging.getLogger("RefactoredAssistant")


class Perception(threading.Thread):
    """
    The Translator: Middleware between Mic and Brain.
    Processes raw audio data into recognized text and metadata.
    """

    def __init__(self, shutdown_signal: GracefulShutdown):
        super().__init__(name="PerceptionThread")
        self.shutdown_signal = shutdown_signal

    def run(self):
        logger.info("Perception started. Translating audio...")
        while not self.shutdown_signal.is_set():
            try:
                # Read from AudioInputQueue
                if not audio_input_queue.empty():
                    audio_data = audio_input_queue.get_nowait()

                    # Simulated processing
                    processed_input = self.process(audio_data)

                    # Push to BrainInputQueue
                    brain_input_queue.put(processed_input)

                    audio_input_queue.task_done()
                    continue
            except queue.Empty:
                pass

            time.sleep(0.1)

        logger.info("Perception stopped.")

    def process(self, audio_data: dict) -> BrainInputEvent:
        """
        Simulate ASR and Voiceprint Recognition.
        """
        content = audio_data.get("content", "")

        # 1. Simulate Whisper ASR latency
        time.sleep(1.0)

        # 2. Simulate Voiceprint (Mock metadata)
        speaker = "User_1"

        result = BrainInputEvent(
            type=InputType.AUDIO,
            text=content,
            user=speaker,
            confidence=0.98,
            language="en"
        )

        logger.info(f"👂 Perception translated audio: {content} (Speaker: {speaker})")
        return result
