"""Main Assistant orchestrator."""

import queue
from typing import Callable, Optional
from .shutdown import GracefulShutdown
from .speaker import SpeakerHandler
from .perception import Perception, PerceptionConfig
from .brain import Brain
from .queues import display_queue, brain_input_queue, InputType, BrainInputEvent

# Import Audio subsystem
from voice_assistant.audio import Audio, AudioConfig


class Assistant:
    """
    Main orchestrator for voice assistant.
    
    Manages:
    - Audio subsystem (mic capture + utterance segmentation)
    - Perception thread (ASR + voiceprint)
    - Brain thread (LLM processing)
    - Speaker thread (TTS playback)
    """

    def __init__(
        self,
        on_exit_request: Optional[Callable[[], None]] = None,
        audio_config: Optional[AudioConfig] = None,
        perception_config: Optional[PerceptionConfig] = None,
    ):
        self.shutdown_signal = GracefulShutdown()
        
        # Audio subsystem (mic + segmentation)
        self.audio = Audio(self.shutdown_signal, audio_config or AudioConfig())
        
        # Perception (ASR + voiceprint) consumes from audio.utterance_queue
        # Uses internal thread pool for parallel ASR + voiceprint execution
        self.perception = Perception(
            self.shutdown_signal,
            utterance_queue=self.audio.utterance_queue,
            config=perception_config or PerceptionConfig(),
        )
        
        # Brain and Speaker (unchanged)
        self.speaker = SpeakerHandler(self.shutdown_signal)
        self.brain = Brain(self.shutdown_signal, self.speaker)
        
        self.on_exit_request = on_exit_request

    def start(self):
        """Start all background threads."""
        self.audio.start()
        self.perception.start()
        self.speaker.start()
        self.brain.start()

    def stop(self):
        """Signal threads to stop and wait for them to join."""
        self.shutdown_signal.stop()
        self.audio.join()
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
