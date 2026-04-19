"""Assistant — pipeline-based orchestrator replacing queue-based Assistant."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..audio.input.types import AudioFrame, AudioSourceFactory
from ..audio.output.types import AudioSinkFactory
from ..llm.profile import create_llm_from_profile
from ..pipeline import Bus, BusMessage, Pipeline, PipelineBuilder
from ..pipeline.event import EventDirection, PipelineEvent
from ..pipeline.observers import (
    AlertDispatcher,
    AlertingObserver,
    AlertThresholds,
    HealthMonitor,
    HealthMonitorConfig,
    InterruptLatencyObserver,
    LatencyObserver,
    MetricsCollector,
    TurnTrackingObserver,
)
from ..pipeline.processors import (
    ASRProcessor,
    ASRSpeakerMerger,
    Brain,
    BrainConfig,
    EchoGuardConfig,
    PlaybackProcessor,
    SpeakerIDProcessor,
    TTSProcessor,
    VADProcessor,
)
from ..plugin import AppConfig
from ..tools.manager import ToolManager
from .events import BrainInputEvent, DisplayMessage, InputType, SignalMessage, UIMessage
from .runtime import RuntimeContext
from .shutdown import GracefulShutdown

logger = logging.getLogger("Assistant")


class Assistant:
    """Pipeline-based voice assistant orchestrator.

    Brain runs as a native Processor inside the pipeline.
    No more QueueWorker threads or RuntimeContext queues —
    the pipeline handles VAD → ASR → Brain → TTS → Playback flow.

    UI messages are pushed via Bus.
    """

    def __init__(
        self,
        app_config: AppConfig | None = None,
        config_path: Path | None = None,
        on_exit_request: Callable[[], None] | None = None,
        audio_source_factory: AudioSourceFactory | None = None,
        audio_sink_factory: AudioSinkFactory | None = None,
    ) -> None:
        registry = self._init_config_and_llm(app_config)
        self._init_bus()
        self._init_tools()

        self.shutdown_signal = GracefulShutdown()
        self.runtime = RuntimeContext.create()

        asr_engine = self._create_engine(registry, "asr")
        tts_engine = self._create_engine(registry, "tts")

        self._init_observers()
        self._pipeline = self._build_pipeline(registry, asr_engine, tts_engine)
        self._init_health_monitor()
        self._init_alerting()

        self._bus.subscribe("speech_start", self._on_speech_start)
        self.on_exit_request = on_exit_request

        self._has_asr = asr_engine is not None
        self._has_tts = tts_engine is not None

    # ------------------------------------------------------------------
    # Initialization helpers (called once from __init__)
    # ------------------------------------------------------------------

    def _init_config_and_llm(self, app_config: AppConfig | None = None) -> object:
        """Load config, LLM, and brain config. Returns registry.

        *app_config* is always provided by the caller (server.py or tests).
        """
        if app_config is None:
            msg = "app_config is required — create via PluginManager + AppConfig in the caller"
            raise ValueError(msg)
        self._app_config = app_config

        profile = self._app_config.get_llm_profile("default")
        self._llm = create_llm_from_profile(profile)

        brain_raw = self._app_config.get_section("brain", {
            "max_history_tokens": 8000,
        })
        self._brain_config = BrainConfig(
            max_history_tokens=brain_raw.get("max_history_tokens", 8000),
        )

        assistant_raw = self._app_config.get_section("assistant", {
            "speech_interrupt_enabled": True,
        })
        self._speech_interrupt_enabled = assistant_raw.get(
            "speech_interrupt_enabled", True
        )

        return self._app_config._registry

    def _init_tools(self) -> None:
        """Create ToolManager — it owns all tool-domain concerns."""
        self._tool_manager = ToolManager(
            app_config=self._app_config,
            bus=self._bus,
            max_history_tokens=self._brain_config.max_history_tokens,
        )

    def _init_bus(self) -> None:
        """Create bus, subscribe UI and playback tracking events."""
        self._bus = Bus()
        self._pipeline: Pipeline | None = None
        self._bus_poll_thread: threading.Thread | None = None
        self._ui_callbacks: list[Callable[[UIMessage], None]] = []

        self._bus.subscribe("ui_message", self._on_ui_bus_message)

        self._brain_active = False
        self._playback_active = False
        self._bus.subscribe("playback_started", self._on_playback_started)
        self._bus.subscribe("playback_ended", self._on_playback_ended)

    def _init_observers(self) -> None:
        """Create latency, turn-tracking, interrupt, and metrics observers."""
        self._latency_observer = LatencyObserver(self._bus)
        self._turn_observer = TurnTrackingObserver(self._bus)
        self._interrupt_observer = InterruptLatencyObserver(self._bus)
        self._metrics_collector = MetricsCollector(self._bus)

    def _build_pipeline(
        self,
        registry: object,
        asr_engine: object | None,
        tts_engine: object | None,
    ) -> Pipeline:
        """Assemble the processor pipeline: VAD → ASR → Brain → TTS → Playback."""
        builder = PipelineBuilder(self._bus)

        echo_guard_cfg = self._build_echo_guard_config(
            self._app_config.get_section("echo_guard")
        )

        self._add_input_processors(builder, registry, asr_engine, echo_guard_cfg)

        agent_graph = self._build_agent_graph()

        self.brain = Brain(
            llm=self._llm,
            tool_manager=self._tool_manager,
            config=self._brain_config,
            bus=self._bus,
            interrupt_event=self.runtime.interrupt_event,
            app_config=self._app_config,
            tts_enabled=tts_engine is not None,
            echo_guard_config=echo_guard_cfg,
            agent_graph=agent_graph,
            approval_manager=self._tool_manager.approval_manager,
        )
        builder.add(self.brain)

        self._add_output_processors(builder, tts_engine)

        return builder.build()

    def _add_input_processors(
        self,
        builder: PipelineBuilder,
        registry: object,
        asr_engine: object | None,
        echo_guard_cfg: EchoGuardConfig,
    ) -> None:
        """Add VAD → ASR (with optional speaker ID fan-out) to the pipeline."""
        self._vad_processor: VADProcessor | None = None
        if asr_engine is None:
            return

        from ..audio.input.types import SegmenterConfig
        from ..audio.input.vad import SileroVAD

        vad = SileroVAD(cfg=SegmenterConfig(), sample_rate=16000)
        self._vad_processor = VADProcessor(
            vad=vad,
            bus=self._bus,
            playback_threshold=(
                echo_guard_cfg.vad_threshold_during_playback
                if echo_guard_cfg.enabled
                else None
            ),
        )
        asr_proc = ASRProcessor(asr=asr_engine, bus=self._bus)

        voiceprint_recognizer = self._create_voiceprint_recognizer(registry)
        if voiceprint_recognizer is not None:
            speaker_id_proc = SpeakerIDProcessor(
                recognizer=voiceprint_recognizer, bus=self._bus
            )
            fan_in_merger = ASRSpeakerMerger(branch_count=2, bus=self._bus)
            builder.add(self._vad_processor)
            builder.fan_out([asr_proc], [speaker_id_proc])
            builder.fan_in(fan_in_merger)
        else:
            builder.add(self._vad_processor)
            builder.add(asr_proc)

    def _add_output_processors(
        self,
        builder: PipelineBuilder,
        tts_engine: object | None,
    ) -> None:
        """Add TTS → Playback processors to the pipeline."""
        self._tts_processor: TTSProcessor | None = None
        self._playback_processor: PlaybackProcessor | None = None
        if tts_engine is not None:
            self._tts_processor = TTSProcessor(tts_engine=tts_engine, bus=self._bus)
            self._playback_processor = PlaybackProcessor(bus=self._bus)
            builder.add(self._tts_processor)
            builder.add(self._playback_processor)

    def _init_health_monitor(self) -> None:
        """Create HealthMonitor from config."""
        hm_raw = self._app_config.get_section("health_monitor", {})
        hm_config = HealthMonitorConfig(
            poll_interval_s=hm_raw.get("poll_interval_s", 5.0),
            stuck_threshold_s=hm_raw.get("stuck_threshold_s", 10.0),
            max_consecutive_failures=hm_raw.get("max_consecutive_failures", 3),
            auto_restart_enabled=hm_raw.get("auto_restart_enabled", True),
            restart_backoff_base_s=hm_raw.get("restart_backoff_base_s", 1.0),
            restart_backoff_max_s=hm_raw.get("restart_backoff_max_s", 30.0),
        )
        self._health_monitor = HealthMonitor(
            pipeline=self._pipeline, bus=self._bus, config=hm_config
        )

    def _init_alerting(self) -> None:
        """Create AlertingObserver and AlertDispatcher from config."""
        alerting_raw = self._app_config.get_section("alerting", {})
        self._alerting_observer = AlertingObserver(
            bus=self._bus,
            thresholds=AlertThresholds(
                latency_spike_multiplier=alerting_raw.get(
                    "latency_spike_multiplier", 2.0
                ),
                latency_spike_consecutive=alerting_raw.get(
                    "latency_spike_consecutive", 5
                ),
                error_rate_threshold=alerting_raw.get("error_rate_threshold", 0.10),
                error_rate_window_s=alerting_raw.get("error_rate_window_s", 300.0),
                queue_saturation_pct=alerting_raw.get("queue_saturation_pct", 0.80),
                queue_saturation_duration_s=alerting_raw.get(
                    "queue_saturation_duration_s", 30.0
                ),
                stuck_approval_timeout_s=alerting_raw.get(
                    "stuck_approval_timeout_s", 300.0
                ),
                alert_cooldown_s=alerting_raw.get("alert_cooldown_s", 60.0),
            )
            if alerting_raw
            else None,
        )

        webhook_url = alerting_raw.get("webhook_url") if alerting_raw else None
        self._alert_dispatcher = AlertDispatcher(
            bus=self._bus, webhook_url=webhook_url
        )

    # ------------------------------------------------------------------
    # Engine / factory helpers
    # ------------------------------------------------------------------

    def _create_engine(self, registry: object, name: str) -> object | None:
        """Create an engine for the given config section, or None if disabled."""
        cfg = self._app_config.get_feature_config(name)
        if not cfg.enabled or not cfg.extension:
            return None
        return registry.instantiate(cfg.extension, cfg.config)  # type: ignore[union-attr]

    def _create_voiceprint_recognizer(self, registry: object) -> object | None:
        """Create VoiceprintRecognizer if speaker ID is enabled, else None."""
        try:
            speaker_cfg = self._app_config.get_feature_config("speaker")
            if not speaker_cfg.enabled or not speaker_cfg.extension:
                return None

            extractor = registry.instantiate(  # type: ignore[union-attr]
                speaker_cfg.extension, speaker_cfg.config
            )
            from ..audio.input.voiceprint_factory import create_voiceprint_recognizer

            return create_voiceprint_recognizer(extractor, speaker_cfg.config)
        except Exception:
            logger.warning("Failed to create voiceprint recognizer", exc_info=True)
            return None

    def _build_agent_graph(self) -> object:
        """Build AgentGraph with a main ChatAgent that has all tools + agent tool."""
        from ..agents.definition import load_agent_definitions
        from ..agents.graph import AgentGraph
        from ..agents.llm_agent import LLMAgent
        from ..agents.runner import AgentRunner

        agents_cfg = self._app_config.get_section("agents") or {}
        llm_profile_name = agents_cfg.get("llm_profile", "default")
        try:
            llm_profile = self._app_config.get_llm_profile(llm_profile_name)
            agent_llm = create_llm_from_profile(llm_profile)
        except (KeyError, ValueError):
            logger.warning(
                "Agent references unknown LLM profile %r — using default",
                llm_profile_name,
            )
            agent_llm = self._llm

        # Load agent definitions from .tank/agents/ directories
        raw_dirs = agents_cfg.get("dirs", ["../agents", "~/.tank/agents"])
        agent_dirs = [Path(d).expanduser().resolve() for d in raw_dirs]
        definitions = load_agent_definitions(agent_dirs)

        # Create AgentRunner
        runner = AgentRunner(
            llm=agent_llm,
            tool_manager=self._tool_manager,
            bus=self._bus,
            approval_manager=self._tool_manager.approval_manager,
            approval_policy=self._tool_manager.approval_policy,
            definitions=definitions,
            max_depth=agents_cfg.get("max_depth", 3),
            max_concurrent=agents_cfg.get("max_concurrent", 5),
        )

        # Register agent tool in ToolManager
        self._tool_manager.set_agent_runner(runner)

        # Build main agent system prompt with available agent types
        agent_catalog = self._build_agent_catalog(definitions)
        system_prompt = agents_cfg.get("system_prompt")
        if system_prompt is None:
            system_prompt = self._build_main_agent_prompt(agent_catalog)

        # Main agent: ALL tools (including agent tool), no exclusions
        main_agent = LLMAgent(
            name="chat",
            llm=agent_llm,
            tool_manager=self._tool_manager,
            system_prompt=system_prompt,
            approval_manager=self._tool_manager.approval_manager,
            approval_policy=self._tool_manager.approval_policy,
        )

        logger.info(
            "AgentGraph built: agent=chat, %d agent definitions loaded",
            len(definitions),
        )
        return AgentGraph(agents={"chat": main_agent}, default_agent="chat")

    @staticmethod
    def _build_agent_catalog(
        definitions: dict[str, object],
    ) -> str:
        """Build a compact catalog of available agents for the system prompt."""
        if not definitions:
            return ""
        lines = []
        for defn in definitions.values():
            entry = f"- {defn.name}: {defn.description}"  # type: ignore[union-attr]
            lines.append(entry)
        return "\n".join(lines)

    @staticmethod
    def _build_main_agent_prompt(agent_catalog: str) -> str:
        """Build the main agent's system prompt."""
        prompt = (
            "You have direct access to all tools including file operations, "
            "shell commands, web search, and more.\n\n"
            "For simple tasks, handle them directly — don't spawn agents "
            "unnecessarily.\n\n"
            "Use the `agent` tool when:\n"
            "- The task is complex and benefits from a specialist's "
            "focused context\n"
            "- You want to run multiple tasks in parallel (call agent "
            "multiple times in one response)\n"
            "- The task needs isolation (experimental changes)\n"
            "- A specific agent has skills relevant to the task\n"
        )
        if agent_catalog:
            prompt += f"\nAvailable agents:\n{agent_catalog}\n"
        return prompt

    def _build_echo_guard_config(self, raw: dict) -> EchoGuardConfig:
        """Build EchoGuardConfig from config.yaml echo_guard section."""
        if not raw:
            return EchoGuardConfig()

        echo_cfg = raw.get("self_echo_detection", {})

        return EchoGuardConfig(
            enabled=raw.get("enabled", True),
            vad_threshold_during_playback=raw.get(
                "vad_threshold_during_playback", 0.85
            ),
            similarity_threshold=echo_cfg.get("similarity_threshold", 0.6),
            window_seconds=echo_cfg.get("window_seconds", 10.0),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_session_id(self, session_id: str) -> None:
        """Resume a specific conversation by ID (legacy compat)."""
        self.brain.resume_conversation(session_id)

    def resume_conversation(self, conversation_id: str) -> bool:
        """Resume a persisted conversation by its UUID. Returns False if not found."""
        return self.brain.resume_conversation(conversation_id)

    def new_conversation(self) -> str:
        """Start a new conversation. Returns new conversation ID."""
        return self.brain.new_conversation()

    @property
    def capabilities(self) -> dict[str, bool]:
        """Feature capabilities for the current session."""
        return {
            "asr": self._has_asr,
            "tts": self._has_tts,
            "speaker_id": self._app_config.is_feature_enabled("speaker"),
        }

    def reload_skills(self) -> dict[str, list[str]]:
        """Rescan skill directories and refresh the system prompt.

        Returns a diff with ``added``, ``removed``, and ``updated`` lists.
        """
        diff = self._tool_manager.reload_skills()
        has_changes = any(diff[k] for k in ("added", "removed", "updated"))
        if has_changes and hasattr(self, "brain"):
            self.brain._context._prompt_assembler.mark_dirty()
        return diff

    @property
    def approval_manager(self):
        """Return the ApprovalManager instance, or None if not configured."""
        return self._tool_manager.approval_manager

    @property
    def metrics(self) -> dict:
        """Return current pipeline metrics snapshot."""
        return self._metrics_collector.snapshot()

    def health_snapshot(self) -> dict:
        """Return health status for this assistant's pipeline."""
        import dataclasses

        result: dict = {"pipeline": None, "alerts": []}
        if self._pipeline is not None:
            ph = self._pipeline.health_snapshot()
            result["pipeline"] = {
                "running": ph.running,
                "is_healthy": ph.is_healthy,
                "processors": [dataclasses.asdict(p) for p in ph.processors],
                "queues": [dataclasses.asdict(q) for q in ph.queues],
            }
        if self._alerting_observer is not None:
            result["alerts"] = self._alerting_observer.snapshot()
        return result

    def subscribe_ui(self, callback: Callable[[UIMessage], None]) -> None:
        """Register a callback for UI messages (replaces polling get_messages)."""
        self._ui_callbacks.append(callback)

    def set_ui_callback(self, callback: Callable[[UIMessage], None]) -> None:
        """Atomically replace all UI callbacks with a single new one.

        Used during WebSocket reattachment to avoid a window where the
        callback list is empty (which would silently drop messages).
        """
        self._ui_callbacks = [callback]

    def clear_ui_callbacks(self) -> None:
        """Remove all UI callbacks (called before rebinding to new WebSocket)."""
        self._ui_callbacks.clear()

    async def start(self) -> None:
        """Start pipeline."""
        await self._tool_manager.connect_mcp_servers()

        if self._pipeline is not None:
            await self._pipeline.start()

        self._bus_poll_thread = threading.Thread(
            target=self._poll_bus_loop, name="BusPoll", daemon=True
        )
        self._bus_poll_thread.start()

        self._health_monitor.start()

        logger.info("Assistant started")

    async def stop(self) -> None:
        """Stop pipeline and cleanup."""
        self.shutdown_signal.stop()

        self._health_monitor.stop()

        if self._pipeline is not None:
            await self._pipeline.stop()

        if self._bus_poll_thread is not None:
            self._bus_poll_thread.join(timeout=2.0)

        await self._tool_manager.cleanup()

        self.brain.close()

        logger.info("Assistant stopped")

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

        self._bus.post(
            BusMessage(
                type="ui_message",
                source="keyboard",
                payload=DisplayMessage(
                    speaker="Keyboard",
                    text=text,
                    is_user=True,
                    is_final=True,
                    msg_id=msg_id,
                ),
            )
        )

        if self._pipeline is not None:
            self._pipeline.push_at(
                "brain",
                BrainInputEvent(
                    type=InputType.TEXT,
                    text=text,
                    user="Keyboard",
                    language=None,
                    confidence=None,
                    metadata={"msg_id": msg_id},
                ),
            )

    def compact_session(self) -> None:
        """Compact Brain conversation history via pipeline (summarize if over budget)."""
        if self._pipeline is not None:
            self._pipeline.push_at(
                "brain",
                BrainInputEvent(
                    type=InputType.SYSTEM,
                    text="__compact__",
                    user="system",
                    language=None,
                    confidence=None,
                ),
            )

    def set_playback_callback(self, callback: Any) -> None:
        """Set the playback callback on the PlaybackProcessor."""
        if self._playback_processor is not None:
            self._playback_processor._playback_callback = callback

    # ------------------------------------------------------------------
    # Internal event handlers
    # ------------------------------------------------------------------

    def _on_ui_bus_message(self, message: BusMessage) -> None:
        """Forward ui_message bus events to registered callbacks."""
        ui_msg: UIMessage = message.payload
        if isinstance(ui_msg, SignalMessage):
            if ui_msg.signal_type == "processing_started":
                self._brain_active = True
            elif ui_msg.signal_type == "processing_ended":
                self._brain_active = False
        for cb in self._ui_callbacks:
            try:
                cb(ui_msg)
            except Exception:
                logger.error("UI callback error", exc_info=True)

    def _on_playback_started(self, _message: BusMessage) -> None:
        self._playback_active = True

    def _on_playback_ended(self, _message: BusMessage) -> None:
        self._playback_active = False

    @property
    def _pipeline_busy(self) -> bool:
        """True when any downstream processor is actively working."""
        return self._brain_active or self._playback_active

    def _on_speech_start(self, _message: BusMessage) -> None:
        """Handle speech_start: interrupt pipeline if busy."""
        if not self._speech_interrupt_enabled:
            return
        if not self._pipeline_busy:
            return
        self._interrupt_pipeline("speech_interrupt")

    def interrupt(self) -> None:
        """Public API: interrupt active processing (e.g. from stop button)."""
        if not self._pipeline_busy:
            return
        self._interrupt_pipeline("client_interrupt")

    def _interrupt_pipeline(self, source: str) -> None:
        """Send interrupt event downstream of ASR, flush those queues, set flag.

        VAD and ASR are left untouched so the user's interrupting speech
        continues to be transcribed while Brain/TTS/Playback are cancelled.
        """
        if self._pipeline is not None:
            logger.info("Interrupt: cancelling active processing (source=%s)", source)
            self._pipeline.send_event_from(
                PipelineEvent(
                    type="interrupt",
                    direction=EventDirection.DOWNSTREAM,
                    source=source,
                ),
                after="asr",
            )
            self._pipeline.flush_from(after="brain")
            self.runtime.interrupt_event.set()

    def _poll_bus_loop(self) -> None:
        """Background thread that polls the bus for pending messages."""
        import time

        while not self.shutdown_signal.is_set():
            self._bus.poll()
            time.sleep(0.02)
        self._bus.poll()
