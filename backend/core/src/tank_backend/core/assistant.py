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
from ..memory import MemoryConfig, MemoryService
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
from ..plugin.manager import PluginManager
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
        config_path: Path | None = None,
        on_exit_request: Callable[[], None] | None = None,
        audio_source_factory: AudioSourceFactory | None = None,
        audio_sink_factory: AudioSinkFactory | None = None,
    ) -> None:
        registry = self._init_config_and_llm()
        self._init_bus()
        self._init_tools()
        self._init_memory()

        self.shutdown_signal = GracefulShutdown()
        self.runtime = RuntimeContext.create()

        asr_engine = self._create_engine(registry, "asr")
        tts_engine = self._create_engine(registry, "tts")

        self._init_bus()
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

    def _init_config_and_llm(self) -> object:
        """Load plugins, config, LLM, and brain config. Returns registry."""
        self._plugin_manager = PluginManager()
        registry = self._plugin_manager.load_all()

        self._app_config = AppConfig(registry=registry)
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

        return registry

    def _init_tools(self) -> None:
        """Create ToolManager — it owns all tool-domain concerns."""
        self._tool_manager = ToolManager(
            app_config=self._app_config,
            bus=self._bus,
        )

        self._checkpointer = self._create_checkpointer()

    def _init_memory(self) -> None:
        """Create optional MemoryService from config.yaml ``memory:`` section."""
        memory_raw = self._app_config.get_section("memory", {"enabled": False})
        memory_config = MemoryConfig.from_dict(memory_raw)

        self._memory_service: MemoryService | None = None
        if not memory_config.enabled:
            return

        # Inherit LLM credentials from the default profile when not explicitly set
        profile = self._app_config.get_llm_profile("default")
        resolved_config = MemoryConfig(
            enabled=True,
            db_path=memory_config.db_path,
            llm_api_key=memory_config.llm_api_key or profile.api_key,
            llm_base_url=memory_config.llm_base_url or profile.base_url,
            llm_model=memory_config.llm_model or "",
            search_limit=memory_config.search_limit,
        )

        try:
            self._memory_service = MemoryService(resolved_config)
            logger.info("Memory service initialised (db_path=%s)", resolved_config.db_path)
        except Exception:
            logger.warning("Failed to initialise memory service — continuing without it",
                           exc_info=True)
            self._memory_service = None

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

        llm_summarization = self._create_summarization_llm()
        agent_graph = self._build_agent_graph()

        self.brain = Brain(
            llm=self._llm,
            tool_manager=self._tool_manager,
            config=self._brain_config,
            bus=self._bus,
            interrupt_event=self.runtime.interrupt_event,
            tts_enabled=tts_engine is not None,
            echo_guard_config=echo_guard_cfg,
            llm_summarization=llm_summarization,
            checkpointer=self._checkpointer,
            agent_graph=agent_graph,
            approval_manager=self._tool_manager.approval_manager,
            memory_service=self._memory_service,
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

    def _create_summarization_llm(self) -> object | None:
        """Create optional summarization LLM from 'summarization' profile, or None."""
        try:
            profile = self._app_config.get_llm_profile("summarization")
            return create_llm_from_profile(profile)
        except (KeyError, ValueError):
            return None

    def _build_agent_graph(self) -> object | None:
        """Build AgentGraph from config.yaml agents: + router: sections, or None.

        If no ``agents:`` section is present in config, returns None and the
        Brain uses its direct LLM path (backward compatible).
        """
        agents_raw = self._app_config.get_section("agents")
        if not agents_raw:
            return None

        from ..agents.graph import AgentGraph

        agents = self._build_agents(agents_raw)
        router = self._build_router()

        logger.info(
            "AgentGraph built: %d agents (%s), %d routes, default=%s",
            len(agents),
            list(agents.keys()),
            len(router.routes),
            router.default_agent,
        )
        return AgentGraph(agents=agents, router=router)

    def _build_agents(
        self,
        agents_raw: dict,
    ) -> dict[str, object]:
        """Instantiate all agents from the agents: config section."""
        from ..agents.factory import create_agent

        agents: dict[str, object] = {}
        for name, agent_cfg in agents_raw.items():
            agent_type = agent_cfg.get("type", "chat")
            llm_profile_name = agent_cfg.get("llm_profile", "default")
            try:
                llm_profile = self._app_config.get_llm_profile(llm_profile_name)
                agent_llm = create_llm_from_profile(llm_profile)
            except (KeyError, ValueError):
                logger.warning(
                    "Agent %r references unknown LLM profile %r — using default",
                    name,
                    llm_profile_name,
                )
                agent_llm = self._llm

            agents[name] = create_agent(
                name=name,
                agent_type=agent_type,
                llm=agent_llm,
                tool_manager=self._tool_manager,
                config=agent_cfg,
                approval_manager=self._tool_manager.approval_manager,
                approval_policy=self._tool_manager.approval_policy,
            )
        return agents

    def _build_router(self) -> object:
        """Build Router from the router: config section."""
        from ..agents.router import Route, Router

        router_raw = self._app_config.get_section("router")
        default_agent = router_raw.get("default", "chat") if router_raw else "chat"
        routes: list[Route] = []

        if router_raw and "routes" in router_raw:
            for route_name, route_cfg in router_raw["routes"].items():
                routes.append(
                    Route(
                        name=route_name,
                        agent_name=route_cfg.get("agent", route_name),
                        keywords=route_cfg.get("keywords", []),
                        description=route_cfg.get("description", ""),
                    )
                )

        router_llm = None
        if router_raw and router_raw.get("llm_profile"):
            try:
                rp = self._app_config.get_llm_profile(router_raw["llm_profile"])
                router_llm = create_llm_from_profile(rp)
            except (KeyError, ValueError):
                logger.warning(
                    "Router LLM profile %r not found", router_raw["llm_profile"]
                )

        return Router(routes=routes, default_agent=default_agent, llm=router_llm)

    def _create_checkpointer(self) -> object | None:
        """Create Checkpointer if persistence is enabled in config, or None."""
        persistence_cfg = self._app_config.get_section("persistence")
        if not persistence_cfg.get("enabled", False):
            return None

        from ..persistence.checkpointer import Checkpointer

        db_path = persistence_cfg.get("db_path", "../data/sessions.db")
        logger.info("Persistence enabled: %s", db_path)
        return Checkpointer(db_path)

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
        """Forward session ID to Brain for checkpoint loading."""
        self.brain.set_session_id(session_id)

    @property
    def capabilities(self) -> dict[str, bool]:
        """Feature capabilities for the current session."""
        return {
            "asr": self._has_asr,
            "tts": self._has_tts,
            "speaker_id": self._app_config.is_feature_enabled("speaker"),
        }

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

        if self._checkpointer is not None:
            self._checkpointer.close()

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

    def reset_session(self) -> None:
        """Reset Brain conversation history via pipeline."""
        if self._pipeline is not None:
            self._pipeline.push_at(
                "brain",
                BrainInputEvent(
                    type=InputType.SYSTEM,
                    text="__reset__",
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
        """Handle speech_start: send interrupt event through pipeline if busy."""
        if not self._speech_interrupt_enabled:
            return
        if not self._pipeline_busy:
            return
        if self._pipeline is not None:
            logger.info("Speech interrupt: cancelling active processing")
            self._pipeline.send_event(
                PipelineEvent(
                    type="interrupt",
                    direction=EventDirection.DOWNSTREAM,
                    source="speech_interrupt",
                )
            )
            self._pipeline.flush_all()
            self.runtime.interrupt_event.set()

    def _poll_bus_loop(self) -> None:
        """Background thread that polls the bus for pending messages."""
        import time

        while not self.shutdown_signal.is_set():
            self._bus.poll()
            time.sleep(0.02)
        self._bus.poll()
