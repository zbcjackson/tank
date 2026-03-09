"""Main Assistant orchestrator."""

import logging
import queue
import uuid
from collections.abc import Callable
from pathlib import Path

from ..audio import AudioInput, AudioInputConfig, AudioOutput, AudioOutputConfig
from ..audio.input.types import AudioSourceFactory
from ..audio.output.types import AudioSinkFactory
from ..config.settings import load_config
from ..llm.profile import create_llm_from_profile
from ..plugin import AppConfig
from ..tools.manager import ToolManager
from .brain import Brain
from .events import BrainInputEvent, DisplayMessage, InputType
from .runtime import RuntimeContext
from .shutdown import GracefulShutdown

logger = logging.getLogger("Assistant")


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
        config_path: Path | None = None,
        on_exit_request: Callable[[], None] | None = None,
        audio_input_config: AudioInputConfig | None = None,
        audio_output_config: AudioOutputConfig | None = None,
        audio_source_factory: AudioSourceFactory | None = None,
        audio_sink_factory: AudioSinkFactory | None = None,
    ):
        # Load configuration
        self._config = load_config(config_path)

        # Create LLM from config.yaml profile and ToolManager
        app_config = AppConfig()
        profile = app_config.get_llm_profile("default")
        self._llm = create_llm_from_profile(profile)
        self._tool_manager = ToolManager(serper_api_key=self._config.serper_api_key)

        self.shutdown_signal = GracefulShutdown()
        self.runtime = RuntimeContext.create()

        # Speech interrupt callback: stop TTS and signal Brain (only when enabled)
        def _on_speech_interrupt() -> None:
            if self._config.speech_interrupt_enabled:
                self.runtime.interrupt_event.set()
                self.audio_output.interrupt()

        # Create voiceprint recognizer if enabled
        self._voiceprint_streaming = None
        if self._config.enable_speaker_id:
            from ..audio.input.voiceprint_factory import create_voiceprint_recognizer
            from ..audio.input.voiceprint_streaming import StreamingVoiceprintRecognizer

            recognizer = create_voiceprint_recognizer(app_config)
            self._voiceprint_streaming = StreamingVoiceprintRecognizer(
                recognizer,
                sample_rate=(audio_input_config or AudioInputConfig()).audio_format.sample_rate,
            )

        # Audio input subsystem (mic + segmentation + perception)
        self.audio_input = AudioInput(
            shutdown_signal=self.shutdown_signal,
            runtime=self.runtime,
            cfg=audio_input_config or AudioInputConfig(),
            app_config=app_config,
            on_speech_interrupt=_on_speech_interrupt,
            source_factory=audio_source_factory,
            voiceprint=self._voiceprint_streaming,
        )

        # Audio output subsystem (TTS playback)
        self.audio_output = AudioOutput(
            shutdown_signal=self.shutdown_signal,
            runtime=self.runtime,
            audio_output_queue=self.runtime.audio_output_queue,
            config=self._config,
            app_config=app_config,
            cfg=audio_output_config or AudioOutputConfig(),
            sink_factory=audio_sink_factory,
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

    _JOIN_TIMEOUT_S = 5.0

    def stop(self):
        """Signal threads to stop, cancel running tasks, and wait for join."""
        self.shutdown_signal.stop()
        self.brain.cancel()
        self.audio_output.cancel()

        timeout = self._JOIN_TIMEOUT_S
        for name, subsystem in [
            ("audio_input", self.audio_input),
            ("audio_output", self.audio_output),
            ("brain", self.brain),
        ]:
            subsystem.join(timeout=timeout)
            if hasattr(subsystem, "is_alive") and subsystem.is_alive():
                logger.warning("%s did not stop within %.1fs, abandoning", name, timeout)

        if self._voiceprint_streaming is not None:
            self._voiceprint_streaming.close()

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

        msg_id = f"kbd_{uuid.uuid4().hex[:8]}"
        self.runtime.ui_queue.put(
            DisplayMessage(
                speaker="Keyboard", text=text, is_user=True, is_final=True, msg_id=msg_id
            )
        )

        self.runtime.brain_input_queue.put(
            BrainInputEvent(
                type=InputType.TEXT,
                text=text,
                user="Keyboard",
                language=None,
                confidence=None,
                metadata={"msg_id": msg_id},
            )
        )

    def get_messages(self):
        """Yields all pending messages from the display queue."""
        while not self.runtime.ui_queue.empty():
            try:
                yield self.runtime.ui_queue.get_nowait()
                self.runtime.ui_queue.task_done()
            except queue.Empty:
                break
