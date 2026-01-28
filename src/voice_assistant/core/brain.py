import threading
import time
import logging
import queue
from .shutdown import GracefulShutdown
from .queues import text_queue, audio_input_queue, audio_output_queue, display_queue
from .speaker import SpeakerHandler

logger = logging.getLogger("RefactoredAssistant")

class Brain(threading.Thread):
    """
    The Orchestrator: Process inputs and decide actions.
    """
    def __init__(self, shutdown_signal: GracefulShutdown, speaker_ref: SpeakerHandler):
        super().__init__(name="BrainThread")
        self.shutdown_signal = shutdown_signal
        self.speaker = speaker_ref

    def run(self):
        logger.info("Brain started. Thinking...")
        while not self.shutdown_signal.is_set():
            # Check Text Queue first (High priority? or User commands)
            try:
                if not text_queue.empty():
                    text_input = text_queue.get_nowait()
                    self.process_text(text_input)
                    text_queue.task_done()
                    continue
            except queue.Empty:
                pass

            # Check Audio Input Queue
            try:
                if not audio_input_queue.empty():
                    audio_input = audio_input_queue.get_nowait()
                    self.process_audio(audio_input)
                    audio_input_queue.task_done()
                    continue
            except queue.Empty:
                pass
            
            # Sleep briefly to avoid busy loop if no inputs
            time.sleep(0.1)

        logger.info("Brain stopped.")

    def process_text(self, text: str):
        logger.info(f"🧠 Processing Text: {text}")
        
        # Check for commands
        if text.lower() == "stop":
            self.speaker.interrupt()
            display_queue.put("System: Speaker interrupted.")
            return

        # Simulate LLM Processing
        display_queue.put(f"Brain: Thinking about '{text}'...")
        time.sleep(2.0) # Simulate network latency
        
        response = f"I processed your text: {text}"
        
        # Send response to UI and Speaker
        display_queue.put(f"Brain Response: {response}")
        audio_output_queue.put({"type": "speech", "content": response})

    def process_audio(self, audio_data: dict):
        content = audio_data.get("content")
        logger.info(f"🧠 Processing Audio: {content}")
        
        # 1. ASR (Already simulated by Mic, but conceptually here)
        transcription = content 
        
        # 2. Logic / LLM
        # If user speaks, we might want to interrupt current speech?
        # For now, let's just queue the response.
        
        time.sleep(1.5) # Simulate processing time
        response = f"I heard you say: {transcription}"
        
        display_queue.put(response)
        audio_output_queue.put({"type": "speech", "content": response})
