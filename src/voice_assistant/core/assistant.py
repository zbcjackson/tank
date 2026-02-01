"""Main Assistant orchestrator."""

import queue
from pathlib import Path
from typing import Callable, Optional
from .shutdown import GracefulShutdown
from .brain import Brain
from .events import InputType, BrainInputEvent
from .runtime import RuntimeContext

# Import Audio subsystem components
from ..audio import AudioInput, AudioInputConfig, AudioOutput, AudioOutputConfig
from ..config.settings import load_config
from ..llm.llm import LLM
from ..tools.manager import ToolManager


class Assistant:
    """
    Main orchestrator for voice assistant.
    
    Manages:
    - Audio input subsystem (mic capture + segmentation + perception)
    - Audio output subsystem (TTS playback)
    - Brain thread (LLM processing)
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        on_exit_request: Optional[Callable[[], None]] = None,
        audio_input_config: Optional[AudioInputConfig] = None,
        audio_output_config: Optional[AudioOutputConfig] = None,
    ):
        # Load configuration
        self._config = load_config(config_path)
        
        # Create LLM and ToolManager
        self._llm = LLM(
            api_key=self._config.llm_api_key,
            model=self._config.llm_model,
            base_url=self._config.llm_base_url,
        )
        self._tool_manager = ToolManager(serper_api_key=self._config.serper_api_key)
        
        self.shutdown_signal = GracefulShutdown()
        self.runtime = RuntimeContext.create()
        
        # Audio input subsystem (mic + segmentation + perception)
        self.audio_input = AudioInput(
            shutdown_signal=self.shutdown_signal,
            runtime=self.runtime,
            cfg=audio_input_config or AudioInputConfig(),
        )
        
        # Audio output subsystem (TTS playback)
        self.audio_output = AudioOutput(
            shutdown_signal=self.shutdown_signal,
            audio_output_queue=self.runtime.audio_output_queue,
            config=self._config,
            cfg=audio_output_config or AudioOutputConfig(),
        )
        
        self.brain = Brain(
            shutdown_signal=self.shutdown_signal,
            runtime=self.runtime,
            speaker_ref=self.audio_output.speaker,
            llm=self._llm,
            tool_manager=self._tool_manager,
            config=self._config,
        )
        
        self.on_exit_request = on_exit_request

    def start(self):
        """Start all background threads."""
        self.audio_input.start()
        self.audio_output.start()
        self.brain.start()

    def stop(self):
        """Signal threads to stop and wait for them to join."""
        self.shutdown_signal.stop()
        self.audio_input.join()
        self.audio_output.join()
        self.brain.join()

    def process_input(self, text: str):
        """Submit user text input for processing."""
        # Filter blank text (defensive check)
        if not text or not text.strip():
            return
        
        if text.lower() in ["quit", "exit"]:
            self.audio_output.speaker.interrupt()
            self.shutdown_signal.stop()
            if self.on_exit_request:
                self.on_exit_request()
            return

        self.runtime.brain_input_queue.put(BrainInputEvent(
            type=InputType.TEXT,
            text=text,
            user="Keyboard",
            language=None,
            confidence=None
        ))

    def get_messages(self):
        """Yields all pending messages from the display queue."""
        while not self.runtime.display_queue.empty():
            try:
                yield self.runtime.display_queue.get_nowait()
                self.runtime.display_queue.task_done()
            except queue.Empty:
                break
