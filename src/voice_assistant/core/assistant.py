import queue
from typing import Callable, Optional
from .shutdown import GracefulShutdown
from .speaker import SpeakerHandler
from .mic import MicHandler
from .perception import Perception
from .brain import Brain
from .queues import display_queue, brain_input_queue, InputType, BrainInputEvent


class Assistant:
    def __init__(self, on_exit_request: Optional[Callable[[], None]] = None):
        self.shutdown_signal = GracefulShutdown()
        self.speaker = SpeakerHandler(self.shutdown_signal)
        self.mic = MicHandler(self.shutdown_signal)
        self.perception = Perception(self.shutdown_signal)
        self.brain = Brain(self.shutdown_signal, self.speaker)
        self.on_exit_request = on_exit_request

    def start(self):
        """Start all background threads."""
        self.mic.start()
        self.perception.start()
        self.speaker.start()
        self.brain.start()

    def stop(self):
        """Signal threads to stop and wait for them to join."""
        self.shutdown_signal.stop()
        self.mic.join()
        self.perception.join()
        self.speaker.join()
        self.brain.join()

    def process_input(self, text: str):
        """Submit user text input for processing."""
        if text.lower() in ["quit", "exit"]:
            if self.on_exit_request:
                self.on_exit_request()
            return

        brain_input_queue.put(BrainInputEvent(
            type=InputType.TEXT,
            text=text,
            user="Keyboard",
            language=None,
            confidence=None
        ))

    def get_messages(self):
        """Yields all pending messages from the display queue."""
        while not display_queue.empty():
            try:
                yield display_queue.get_nowait()
                display_queue.task_done()
            except queue.Empty:
                break