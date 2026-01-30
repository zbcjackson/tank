import logging
import time

from .events import BrainInputEvent, DisplayMessage
from .runtime import RuntimeContext
from .shutdown import StopSignal
from .worker import QueueWorker
from ..audio.output import SpeakerHandler

logger = logging.getLogger("RefactoredAssistant")


class Brain(QueueWorker[BrainInputEvent]):
    """
    The Orchestrator: Process inputs and decide actions.
    
    Consumes BrainInputEvent from brain_input_queue and processes them.
    """
    
    def __init__(
        self,
        shutdown_signal: StopSignal,
        runtime: RuntimeContext,
        speaker_ref: SpeakerHandler,
    ):
        super().__init__(
            name="BrainThread",
            stop_signal=shutdown_signal,
            input_queue=runtime.brain_input_queue,
            poll_interval_s=0.1,
        )
        self._runtime = runtime
        self.speaker = speaker_ref

    def run(self) -> None:
        logger.info("Brain started. Thinking...")
        try:
            super().run()
        finally:
            logger.info("Brain stopped.")

    def handle(self, event: BrainInputEvent) -> None:
        """
        Handles inputs from both Keyboard and Perception.
        """
        logger.info(f"🧠 Processing {event.type} from {event.user}: {event.text}")

        # Simulate LLM Processing
        self._runtime.display_queue.put(
            DisplayMessage(speaker="Brain", text=f"Thinking about '{event.text}'...")
        )
        time.sleep(2.0)  # Simulate network latency

        response = f"I processed your input: {event.text}"

        # Send response to UI and Speaker
        self._runtime.display_queue.put(DisplayMessage(speaker="Brain", text=response))
        self._runtime.audio_output_queue.put({"type": "speech", "content": response})
