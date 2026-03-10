"""Main Assistant orchestrator."""

import asyncio
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
from ..plugin.manager import PluginManager
from ..sandbox.config import SandboxConfig
from ..sandbox.manager import SandboxManager
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
    - Audio input subsystem (mic capture + segmentation + perception)  [optional]
    - Audio output subsystem (TTS playback)  [optional]
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

        # 1. Load plugins and build registry
        self._plugin_manager = PluginManager()
        registry = self._plugin_manager.load_all()

        # 2. Load and validate config against registry
        self._app_config = AppConfig(registry=registry)
        profile = self._app_config.get_llm_profile("default")
        self._llm = create_llm_from_profile(profile)
        self._tool_manager = ToolManager(serper_api_key=self._config.serper_api_key)

        # Sandbox (lazy Docker container for runtime tools)
        sandbox_raw = app_config._config.get("sandbox", {})
        sandbox_config = SandboxConfig.from_dict(sandbox_raw)
        self._sandbox: SandboxManager | None = None
        if sandbox_config.enabled:
            self._sandbox = SandboxManager(sandbox_config)
            self._tool_manager.register_sandbox_tools(self._sandbox)
            logger.info("Sandbox tools registered (container created lazily)")

        self.shutdown_signal = GracefulShutdown()
        self.runtime = RuntimeContext.create()

        asr_enabled = self._app_config.is_slot_enabled("asr")
        tts_enabled = self._app_config.is_slot_enabled("tts")

        # Speech interrupt callback: stop TTS and signal Brain (only when enabled)
        def _on_speech_interrupt() -> None:
            if self._config.speech_interrupt_enabled:
                self.runtime.interrupt_event.set()
                if self.audio_output is not None:
                    self.audio_output.interrupt()

        # 3. Instantiate engines via registry
        asr_engine = None
        if asr_enabled:
            slot = self._app_config.get_slot_config("asr")
            asr_engine = registry.instantiate(slot.extension, slot.config)

        tts_engine = None
        if tts_enabled:
            slot = self._app_config.get_slot_config("tts")
            tts_engine = registry.instantiate(slot.extension, slot.config)

        # Create voiceprint recognizer if enabled
        self._voiceprint_streaming = None
        if self._config.enable_speaker_id and self._app_config.is_slot_enabled("speaker"):
            from ..audio.input.voiceprint_factory import create_voiceprint_recognizer
            from ..audio.input.voiceprint_streaming import StreamingVoiceprintRecognizer

            speaker_slot = self._app_config.get_slot_config("speaker")
            speaker_extractor = registry.instantiate(
                speaker_slot.extension, speaker_slot.config
            )
            recognizer = create_voiceprint_recognizer(
                speaker_extractor, speaker_slot.config
            )
            self._voiceprint_streaming = StreamingVoiceprintRecognizer(
                recognizer,
                sample_rate=(audio_input_config or AudioInputConfig()).audio_format.sample_rate,
            )

        # 4. Pass pre-built engines to subsystems
        self.audio_input: AudioInput | None = None
        if asr_engine is not None:
            self.audio_input = AudioInput(
                shutdown_signal=self.shutdown_signal,
                runtime=self.runtime,
                cfg=audio_input_config or AudioInputConfig(),
                asr_engine=asr_engine,
                on_speech_interrupt=_on_speech_interrupt,
                source_factory=audio_source_factory,
                voiceprint=self._voiceprint_streaming,
            )

        self.audio_output: AudioOutput | None = None
        if tts_engine is not None:
            self.audio_output = AudioOutput(
                shutdown_signal=self.shutdown_signal,
                runtime=self.runtime,
                audio_output_queue=self.runtime.audio_output_queue,
                config=self._config,
                tts_engine=tts_engine,
                cfg=audio_output_config or AudioOutputConfig(),
                sink_factory=audio_sink_factory,
            )

        self.brain = Brain(
            shutdown_signal=self.shutdown_signal,
            runtime=self.runtime,
            speaker_ref=self.audio_output,
            llm=self._llm,
            tool_manager=self._tool_manager,
            config=self._config,
            tts_enabled=tts_enabled,
        )

        self.on_exit_request = on_exit_request

    @property
    def capabilities(self) -> dict[str, bool]:
        """Feature capabilities for the current session."""
        return {
            "asr": self.audio_input is not None,
            "tts": self.audio_output is not None,
            "speaker_id": (
                self._config.enable_speaker_id
                and self._app_config.is_slot_enabled("speaker")
            ),
        }

    def start(self):
        """Start all background threads."""
        if self.audio_input is not None:
            self.audio_input.start()
        if self.audio_output is not None:
            self.audio_output.start()
        self.brain.start()

    _JOIN_TIMEOUT_S = 5.0

    def stop(self):
        """Signal threads to stop, cancel running tasks, and wait for join."""
        self.shutdown_signal.stop()
        self.brain.cancel()
        if self.audio_output is not None:
            self.audio_output.cancel()

        timeout = self._JOIN_TIMEOUT_S
        subsystems: list[tuple[str, object]] = [("brain", self.brain)]
        if self.audio_input is not None:
            subsystems.insert(0, ("audio_input", self.audio_input))
        if self.audio_output is not None:
            subsystems.insert(1, ("audio_output", self.audio_output))

        for name, subsystem in subsystems:
            subsystem.join(timeout=timeout)
            if hasattr(subsystem, "is_alive") and subsystem.is_alive():
                logger.warning("%s did not stop within %.1fs, abandoning", name, timeout)

        if self._voiceprint_streaming is not None:
            self._voiceprint_streaming.close()

        # Cleanup sandbox container
        if self._sandbox is not None and self._sandbox.is_running:
            try:
                asyncio.run(self._sandbox.cleanup())
            except RuntimeError:
                # Already inside an event loop — schedule instead
                loop = asyncio.get_event_loop()
                loop.create_task(self._sandbox.cleanup())

    def process_input(self, text: str):
        """Submit user text input for processing."""
        # Filter blank text (defensive check)
        if not text or not text.strip():
            return

        if text.lower() in ["quit", "exit"]:
            if self.audio_output is not None:
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
