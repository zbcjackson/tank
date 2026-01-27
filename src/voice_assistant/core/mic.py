import threading
import time
import random
import logging
from .shutdown import GracefulShutdown
from .queues import audio_input_queue

logger = logging.getLogger("RefactoredAssistant")

class MicHandler(threading.Thread):
    """
    The Ear: Continuously listens to the microphone.
    """
    def __init__(self, shutdown_signal: GracefulShutdown):
        super().__init__(name="MicThread")
        self.shutdown_signal = shutdown_signal
        self.simulated_phrases = [
            "What is the weather?",
            "Tell me a joke.",
            "Who are you?",
            "Set a timer for 5 minutes."
        ]

    def run(self):
        logger.info("MicHandler started. Listening...")
        while not self.shutdown_signal.is_set():
            # Simulate listening activity
            time.sleep(random.uniform(5, 15))  # Listen for a random time
            
            if self.shutdown_signal.is_set():
                break

            # Simulate voice detection
            detected_audio = random.choice(self.simulated_phrases)
            logger.info(f"🎤 Detected voice input (Simulated): '{detected_audio}'")
            
            # Push to AudioInputQueue
            # In a real system, this would be raw bytes or a numpy array
            audio_input_queue.put({"type": "audio", "content": detected_audio})
            
        logger.info("MicHandler stopped.")
