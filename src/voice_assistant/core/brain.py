import threading
import time
import logging
import queue
from .shutdown import StopSignal
from .events import BrainInputEvent
from .runtime import RuntimeContext
from ..audio.output import SpeakerHandler

logger = logging.getLogger("RefactoredAssistant")

class Brain(threading.Thread):
    """
    The Orchestrator: Process inputs and decide actions.
    """
    def __init__(self, shutdown_signal: StopSignal, runtime: RuntimeContext, speaker_ref: SpeakerHandler):
        super().__init__(name="BrainThread")
        self.shutdown_signal = shutdown_signal
        self._runtime = runtime
        self.speaker = speaker_ref

    def run(self):
        logger.info("Brain started. Thinking...")
        while not self.shutdown_signal.is_set():
            # The Brain now reads from a single BrainInputQueue
            try:
                if not self._runtime.brain_input_queue.empty():
                    raw_input = self._runtime.brain_input_queue.get_nowait()
                    self.process_input(raw_input)
                    self._runtime.brain_input_queue.task_done()
                    continue
            except queue.Empty:
                pass
            
            # Sleep briefly to avoid busy loop if no inputs
            time.sleep(0.1)

        logger.info("Brain stopped.")

    def process_input(self, data: BrainInputEvent):
        """
        Handles inputs from both Keyboard and Perception.
        """
        logger.info(f"🧠 Processing {data.type} from {data.user}: {data.text}")

        # Check for commands
        if data.text.lower() == "stop":
            self.speaker.interrupt()
            self._runtime.display_queue.put("System: Speaker interrupted.")
            return

        # Simulate LLM Processing
        self._runtime.display_queue.put(f"Brain: Thinking about '{data.text}'...")
        time.sleep(2.0) # Simulate network latency
        
        response = f"I processed your input: {data.text}"
        
        # Send response to UI and Speaker
        self._runtime.display_queue.put(f"{response}")
        self._runtime.audio_output_queue.put({"type": "speech", "content": response})
