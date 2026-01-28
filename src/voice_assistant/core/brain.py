import threading
import time
import logging
import queue
import json
from .shutdown import GracefulShutdown
from .queues import brain_input_queue, audio_output_queue, display_queue
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
            # The Brain now reads from a single BrainInputQueue
            try:
                if not brain_input_queue.empty():
                    raw_input = brain_input_queue.get_nowait()
                    self.process_input(raw_input)
                    brain_input_queue.task_done()
                    continue
            except queue.Empty:
                pass
            
            # Sleep briefly to avoid busy loop if no inputs
            time.sleep(0.1)

        logger.info("Brain stopped.")

    def process_input(self, raw_data: str):
        """
        Handles inputs from both Keyboard and Perception.
        """
        try:
            # Try to parse as JSON (Perception output)
            data = json.loads(raw_data)
            input_type = data.get("type")
            text = data.get("text", "")
            speaker = data.get("metadata", {}).get("speaker", "Unknown")
            logger.info(f"🧠 Processing {input_type} from {speaker}: {text}")
        except (json.JSONDecodeError, TypeError):
            # Assume it's plain text from Keyboard
            text = raw_data
            logger.info(f"🧠 Processing Keyboard Input: {text}")

        # Check for commands
        if text.lower() == "stop":
            self.speaker.interrupt()
            display_queue.put("System: Speaker interrupted.")
            return

        # Simulate LLM Processing
        display_queue.put(f"Brain: Thinking about '{text}'...")
        time.sleep(2.0) # Simulate network latency
        
        response = f"I processed your input: {text}"
        
        # Send response to UI and Speaker
        display_queue.put(f"Brain Response: {response}")
        audio_output_queue.put({"type": "speech", "content": response})
