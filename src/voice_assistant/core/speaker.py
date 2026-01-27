import threading
import time
import logging
import queue
from .shutdown import GracefulShutdown
from .queues import audio_output_queue

logger = logging.getLogger("RefactoredAssistant")

class SpeakerHandler(threading.Thread):
    """
    The Mouth: Continuously checks AudioOutputQueue and plays audio.
    Supports interruption.
    """
    def __init__(self, shutdown_signal: GracefulShutdown):
        super().__init__(name="SpeakerThread")
        self.shutdown_signal = shutdown_signal
        self.interrupt_event = threading.Event()

    def interrupt(self):
        """Signal to stop current playback immediately."""
        self.interrupt_event.set()
        # Also clear the queue of pending audio to fully reset
        with audio_output_queue.mutex:
            audio_output_queue.queue.clear()
        logger.warning("🚫 Speaker Interrupted!")

    def run(self):
        logger.info("SpeakerHandler started. Waiting for audio...")
        while not self.shutdown_signal.is_set():
            try:
                # Wait for audio data with timeout to check shutdown signal
                item = audio_output_queue.get(timeout=0.5)
                
                if item:
                    text_to_speak = item.get("content", "")
                    logger.info(f"🔊 Starting playback: '{text_to_speak}'")
                    
                    # Simulate playback chunk by chunk to allow interruption
                    # Assume roughly 0.1s per character for simulation
                    duration = len(text_to_speak) * 0.1
                    chunks = int(duration / 0.1)
                    
                    self.interrupt_event.clear() # Reset interrupt flag
                    
                    for _ in range(chunks):
                        if self.shutdown_signal.is_set() or self.interrupt_event.is_set():
                            logger.info("Playback stopped early.")
                            break
                        time.sleep(0.1)
                    
                    if not self.interrupt_event.is_set():
                        logger.info("✅ Playback finished.")
                    
                    audio_output_queue.task_done()
            
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Speaker error: {e}")

        logger.info("SpeakerHandler stopped.")
