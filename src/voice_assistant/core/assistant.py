import queue
from typing import Callable, Optional
from .shutdown import GracefulShutdown
from .speaker import SpeakerHandler
from .mic import MicHandler
from .brain import Brain
from .queues import display_queue, text_queue

class Assistant:
    def __init__(self, on_exit_request: Optional[Callable[[], None]] = None):
        self.shutdown_signal = GracefulShutdown()
        self.speaker = SpeakerHandler(self.shutdown_signal)
        self.mic = MicHandler(self.shutdown_signal)
        self.brain = Brain(self.shutdown_signal, self.speaker)
        self.on_exit_request = on_exit_request

    def start(self):
        """Start all background threads."""
        self.mic.start()
        self.speaker.start()
        self.brain.start()

    def stop(self):
        """Signal threads to stop and wait for them to join."""
        self.shutdown_signal.stop()
        self.mic.join()
        self.speaker.join()
        self.brain.join()

    def process_input(self, text: str):
        """Submit user text input for processing."""
        if text.lower() in ["quit", "exit"]:
            if self.on_exit_request:
                self.on_exit_request()
            return

        text_queue.put(text)

    def get_messages(self):
        """Yields all pending messages from the display queue."""
        while not display_queue.empty():
            try:
                yield display_queue.get_nowait()
                display_queue.task_done()
            except queue.Empty:
                break