"""AssistantV2 — pipeline-based orchestrator replacing queue-based Assistant."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..audio.input.types import AudioFrame, AudioSourceFactory
from ..audio.output.types import AudioSinkFactory
from ..config.settings import load_config
from ..llm.profile import create_llm_from_profile
from ..pipeline import Bus, BusMessage, Pipeline, PipelineBuilder
from ..pipeline.event import EventDirection, PipelineEvent
from ..pipeline.observers import InterruptLatencyObserver, LatencyObserver, TurnTrackingObserver
from ..pipeline.wrappers import (
    ASRProcessor,
    BrainProcessor,
    PlaybackProcessor,
    TTSProcessor,
    VADProcessor,
)
from ..plugin import AppConfig
from ..plugin.manager import PluginManager
from ..sandbox.config import SandboxConfig
from ..sandbox.manager import SandboxManager
from ..tools.manager import ToolManager
from .brain import Brain
from .events import BrainInputEvent, DisplayMessage, InputType, UIMessage
from .runtime import RuntimeContext
from .shutdown import GracefulShutdown

logger = logging.getLogger("AssistantV2")


class AssistantV2:
    """Pipeline-based voice assistant orchestrator.

    Replaces the old Assistant's hardcoded queue orchestration with
    PipelineBuilder. Brain still runs as a QueueWorker thread; the
    pipeline handles VAD → ASR → Brain → TTS → Playback flow.

    UI messages are pushed via Bus instead of polled from ui_queue.
    """

    def __init__(
        self,
        config_path: Path | None = None,
        on_exit_request: Callable[[], None] | None = None,
        audio_source_factory: AudioSourceFactory | None = None,
        audio_sink_factory: AudioSinkFactory | None = None,
    ) -> None:
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
        sandbox_raw = self._app_config._config.get("sandbox", {})
        sandbox_config = SandboxConfig.from_dict(sandbox_raw)
        self._sandbox: SandboxManager | None = None
        if sandbox_config.enabled:
            self._sandbox = SandboxManager(sandbox_config)
            self._tool_manager.register_sandbox_tools(self._sandbox)
            logger.info("Sandbox tools registered (container created lazily)")

        self.shutdown_signal = GracefulShutdown()
        self.runtime = RuntimeContext.create()

        # 3. Instantiate engines via registry
        asr_engine = self._create_engine(registry, "asr")
        tts_engine = self._create_engine(registry, "tts")

        # 4. Build pipeline
        self._bus = Bus()
        self._pipeline: Pipeline | None = None
        self._bus_poll_thread: threading.Thread | None = None
        self._ui_callbacks: list[Callable[[UIMessage], None]] = []

        # Subscribe to ui_message on bus → forward to registered callbacks
        self._bus.subscribe("ui_message", self._on_ui_bus_message)

        # Observers
        self._latency_observer = LatencyObserver(self._bus)
        self._turn_observer = TurnTrackingObserver(self._bus)
        self._interrupt_observer = InterruptLatencyObserver(self._bus)

        # Build processors
        builder = PipelineBuilder(self._bus)

        # VAD processor (needs SileroVAD instance)
        self._vad_processor: VADProcessor | None = None
        if asr_engine is not None:
            from ..audio.input.types import SegmenterConfig
            from ..audio.input.vad import SileroVAD

            vad = SileroVAD(cfg=SegmenterConfig(), sample_rate=16000)
            self._vad_processor = VADProcessor(vad=vad, bus=self._bus)
            asr_proc = ASRProcessor(asr=asr_engine, bus=self._bus)
            builder.add(self._vad_processor)
            builder.add(asr_proc)

        # Brain (still a QueueWorker thread for async LLM)
        self.brain = Brain(
            shutdown_signal=self.shutdown_signal,
            runtime=self.runtime,
            speaker_ref=None,  # No direct AudioOutput ref in V2
            llm=self._llm,
            tool_manager=self._tool_manager,
            config=self._config,
            tts_enabled=tts_engine is not None,
        )
        brain_proc = BrainProcessor(
            brain=self.brain, bus=self._bus, runtime=self.runtime
        )
        builder.add(brain_proc)

        # TTS + Playback
        self._tts_processor: TTSProcessor | None = None
        self._playback_processor: PlaybackProcessor | None = None
        if tts_engine is not None:
            self._tts_processor = TTSProcessor(tts_engine=tts_engine, bus=self._bus)
            self._playback_processor = PlaybackProcessor(bus=self._bus)
            builder.add(self._tts_processor)
            builder.add(self._playback_processor)

        self._pipeline = builder.build()

        # Speech interrupt: speech_start → send interrupt event upstream
        self._bus.subscribe("speech_start", self._on_speech_start)

        self.on_exit_request = on_exit_request

        # Store factories for capability reporting
        self._has_asr = asr_engine is not None
        self._has_tts = tts_engine is not None

    def _create_engine(self, registry: object, name: str) -> object | None:
        """Create an engine for the given config section, or None if disabled."""
        cfg = self._app_config.get_feature_config(name)
        if not cfg.enabled or not cfg.extension:
            return None
        return registry.instantiate(cfg.extension, cfg.config)  # type: ignore[union-attr]

    @property
    def capabilities(self) -> dict[str, bool]:
        """Feature capabilities for the current session."""
        return {
            "asr": self._has_asr,
            "tts": self._has_tts,
            "speaker_id": (
                self._config.enable_speaker_id
                and self._app_config.is_feature_enabled("speaker")
            ),
        }

    def subscribe_ui(self, callback: Callable[[UIMessage], None]) -> None:
        """Register a callback for UI messages (replaces polling get_messages)."""
        self._ui_callbacks.append(callback)

    def _on_ui_bus_message(self, message: BusMessage) -> None:
        """Forward ui_message bus events to registered callbacks."""
        ui_msg: UIMessage = message.payload
        for cb in self._ui_callbacks:
            try:
                cb(ui_msg)
            except Exception:
                logger.error("UI callback error", exc_info=True)

    def _on_speech_start(self, _message: BusMessage) -> None:
        """Handle speech_start: send interrupt event through pipeline."""
        if not self._config.speech_interrupt_enabled:
            return
        if self._pipeline is not None:
            self._pipeline.send_event(
                PipelineEvent(
                    type="interrupt",
                    direction=EventDirection.DOWNSTREAM,
                    source="speech_interrupt",
                )
            )
            self._pipeline.flush_all()
            self.runtime.interrupt_event.set()

    async def start(self) -> None:
        """Start pipeline and Brain thread."""
        if self._pipeline is not None:
            await self._pipeline.start()

        # Brain still runs as its own QueueWorker thread
        self.brain.start()

        # Start bus polling thread
        self._bus_poll_thread = threading.Thread(
            target=self._poll_bus_loop, name="BusPoll", daemon=True
        )
        self._bus_poll_thread.start()

        logger.info("AssistantV2 started")

    def _poll_bus_loop(self) -> None:
        """Background thread that polls the bus for pending messages."""
        import time

        while not self.shutdown_signal.is_set():
            self._bus.poll()
            time.sleep(0.02)  # 20ms poll interval
        # Final drain
        self._bus.poll()

    async def stop(self) -> None:
        """Stop pipeline, Brain, and cleanup."""
        self.shutdown_signal.stop()
        self.brain.cancel()

        if self._pipeline is not None:
            await self._pipeline.stop()

        self.brain.join(timeout=5.0)
        if self.brain.is_alive():
            logger.warning("Brain did not stop within 5s")

        # Wait for bus poll thread
        if self._bus_poll_thread is not None:
            self._bus_poll_thread.join(timeout=2.0)

        # Cleanup sandbox
        if self._sandbox is not None and self._sandbox.is_running:
            await self._sandbox.cleanup()

        logger.info("AssistantV2 stopped")

    def push_audio(self, frame: AudioFrame) -> None:
        """Push an audio frame into the pipeline (entry point for mic data)."""
        if self._pipeline is not None:
            self._pipeline.push(frame)

    def process_input(self, text: str) -> None:
        """Submit user text input for processing."""
        if not text or not text.strip():
            return

        if text.lower() in ("quit", "exit"):
            self.shutdown_signal.stop()
            if self.on_exit_request:
                self.on_exit_request()
            return

        msg_id = f"kbd_{uuid.uuid4().hex[:8]}"

        # Post user message to UI via bus
        self._bus.post(BusMessage(
            type="ui_message",
            source="keyboard",
            payload=DisplayMessage(
                speaker="Keyboard",
                text=text,
                is_user=True,
                is_final=True,
                msg_id=msg_id,
            ),
        ))

        # Feed to Brain via its input queue
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

    def reset_session(self) -> None:
        """Reset Brain conversation history."""
        self.runtime.brain_input_queue.put(
            BrainInputEvent(
                type=InputType.SYSTEM,
                text="__reset__",
                user="system",
                language=None,
                confidence=None,
            )
        )

    def set_playback_callback(self, callback: Any) -> None:
        """Set the playback callback on the PlaybackProcessor."""
        if self._playback_processor is not None:
            self._playback_processor._playback_callback = callback
