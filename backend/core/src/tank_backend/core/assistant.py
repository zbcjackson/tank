"""Assistant — pipeline-based orchestrator replacing queue-based Assistant."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..audio.input.types import AudioFrame
from ..config import AppConfig
from ..config.context import AppContext
from ..config.models import EchoGuardConfig
from ..llm.capabilities import resolve_capabilities_sync
from ..llm.profile import create_llm_from_profile
from ..pipeline import Bus, BusMessage, Pipeline, PipelineBuilder
from ..pipeline.event import EventDirection, PipelineEvent
from ..pipeline.observers import (
    AlertDispatcher,
    AlertingObserver,
    AlertThresholds,
    HealthMonitor,
    InterruptLatencyObserver,
    LatencyObserver,
    MetricsCollector,
    TitleGenerationObserver,
    TurnTrackingObserver,
)
from ..pipeline.processors import (
    ASRProcessor,
    ASRSpeakerMerger,
    Brain,
    PlaybackProcessor,
    SpeakerIDProcessor,
    TTSProcessor,
    VADProcessor,
)
from ..plugin.registry import ExtensionRegistry
from ..tools.manager import ToolManager
from .content import ContentBlocks
from .events import BrainInputEvent, DisplayMessage, InputType, SignalMessage, UIMessage
from .runtime import RuntimeContext
from .shutdown import GracefulShutdown

if TYPE_CHECKING:
    from tank_contracts import ASREngine, TTSEngine

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
        app_context: AppContext,
        *,
        on_exit_request: Callable[[], None] | None = None,
        wants_audio_input: bool = True,
        wants_audio_output: bool = True,
    ) -> None:

        self._app_context = app_context
        self._channel_store = app_context.channel_store
        self._conversation_store = app_context.conversation_store
        self._compaction_store = app_context.compaction_store
        self._messages_store = app_context.conversation_messages_store
        self._media_store = app_context.media_store
        self._worker_store = app_context.worker_store
        registry = self._init_config_and_llm(app_context.app_config, registry=app_context.registry)
        self._init_bus()
        self._init_tools()

        # Wire job management tool if scheduler is enabled
        if app_context.job_store is not None and app_context.scheduler is not None:
            self._tool_manager.set_job_manager(app_context.job_store, app_context.scheduler)

        self.shutdown_signal = GracefulShutdown()
        self.runtime = RuntimeContext.create()

        self._voiceprint_recognizer = app_context.voiceprint_recognizer

        # Text-only sessions (e.g. chat-platform connectors) opt out of the
        # audio legs so the pipeline doesn't burn cycles running VAD/ASR on
        # silence or generating TTS chunks nobody hears. Overriding the
        # engines locally cascades through the ``_add_*_processors``
        # gates — no VAD/ASR/TTS/Playback processor is ever built, and the
        # Brain stops emitting ``AudioOutputRequest``.
        asr_engine = app_context.asr_engine if wants_audio_input else None
        tts_engine = app_context.tts_engine if wants_audio_output else None
        self._wants_audio_input = wants_audio_input
        self._wants_audio_output = wants_audio_output

        self._init_observers()
        self._pipeline = self._build_pipeline(registry, asr_engine, tts_engine)
        self._init_health_monitor()
        self._init_alerting()

        self._bus.subscribe("speech_detected", self._on_speech_detected)
        self.on_exit_request = on_exit_request

        self._has_asr = asr_engine is not None
        self._has_tts = tts_engine is not None

    # ------------------------------------------------------------------
    # Initialization helpers (called once from __init__)
    # ------------------------------------------------------------------

    def _init_config_and_llm(
        self, app_config: AppConfig | None = None, registry: ExtensionRegistry | None = None
    ) -> ExtensionRegistry:
        """Load config, LLM, and brain config. Returns registry.

        *app_config* is always provided by the caller (server.py or tests).
        """
        if app_config is None:
            msg = "app_config is required — create via PluginManager + AppConfig in the caller"
            raise ValueError(msg)
        self._app_config = app_config

        profile = self._app_config.get_llm_profile("default")
        self._llm = create_llm_from_profile(profile)
        self._llm_capabilities = resolve_capabilities_sync(profile)
        logger.info(
            "Resolved LLM capabilities for %s: modalities=%s source=%s",
            self._llm_capabilities.model_id,
            sorted(self._llm_capabilities.input_modalities),
            self._llm_capabilities.source.value,
        )

        self._brain_config = self._app_config.brain

        self._speech_interrupt_enabled = self._app_config.assistant.speech_interrupt_enabled

        assert registry is not None
        return registry

    def _init_tools(self) -> None:
        """Create ToolManager — it owns all tool-domain concerns."""
        self._tool_manager = ToolManager(
            app_config=self._app_config,
            bus=self._bus,
            max_history_tokens=self._brain_config.max_history_tokens,
            # Phase 18: thread the session-scoped MediaStore so tools
            # opting into ``ToolContext`` (e.g. ChartTool) can persist
            # binary content. ``set_session_id`` below propagates the
            # current session id at conversation-resume time.
            media_store=self._media_store,
        )
        # Phase 17 refactor: subscribe ToolOutputObserver to the
        # generic ``tool_completed`` event ToolManager publishes.
        # Keeps content-kind awareness (ImageBlock today, audio/doc
        # later) out of ToolManager. The observer's lifetime matches
        # the assistant's; no explicit teardown is needed because the
        # bus's subscriber list is GC'd with the assistant.
        from ..connectors.tool_output_observer import ToolOutputObserver
        self._tool_output_observer = ToolOutputObserver(self._bus)

    def _init_bus(self) -> None:
        """Create bus, subscribe UI and playback tracking events."""
        self._bus = Bus()
        self._pipeline: Pipeline | None = None
        self._bus_poll_thread: threading.Thread | None = None
        self._ui_callbacks: list[Callable[[UIMessage], None]] = []

        self._bus.subscribe("ui_message", self._on_ui_bus_message)

        self._brain_active = False
        self._brain_idle_event = asyncio.Event()
        self._brain_idle_event.set()  # starts idle
        self._event_loop: asyncio.AbstractEventLoop | None = None

        self._playback_active = False
        self._bus.subscribe("playback_started", self._on_playback_started)
        self._bus.subscribe("playback_ended", self._on_playback_ended)

    def _init_observers(self) -> None:
        """Create latency, turn-tracking, interrupt, and metrics observers."""
        self._latency_observer = LatencyObserver(self._bus)
        self._turn_observer = TurnTrackingObserver(self._bus)
        self._interrupt_observer = InterruptLatencyObserver(self._bus)
        self._metrics_collector = MetricsCollector(self._bus)
        self._title_observer: TitleGenerationObserver | None = None
        title_generator = self._app_context.title_generator
        if title_generator is not None:
            self._title_observer = TitleGenerationObserver(
                bus=self._bus, generator=title_generator,
                on_title_generated=self._on_title_generated,
            )

    def _build_pipeline(
        self,
        registry: ExtensionRegistry,
        asr_engine: ASREngine | None,
        tts_engine: TTSEngine | None,
    ) -> Pipeline:
        """Assemble the processor pipeline: VAD → ASR → Brain → TTS → Playback."""
        builder = PipelineBuilder(self._bus)

        echo_guard_cfg = self._app_config.echo_guard

        self._add_input_processors(builder, registry, asr_engine, echo_guard_cfg)

        self.brain = Brain(
            llm=self._llm,
            tool_manager=self._tool_manager,
            config=self._brain_config,
            bus=self._bus,
            interrupt_event=self.runtime.interrupt_event,
            app_config=self._app_config,
            tts_enabled=tts_engine is not None,
            echo_guard_config=echo_guard_cfg,
            channel_store=self._channel_store,
            conversation_store=self._conversation_store,
            compaction_store=self._compaction_store,
            messages_store=self._messages_store,
            media_store=self._media_store,
            llm_capabilities=self._llm_capabilities.input_modalities,
            worker_store=self._worker_store,
        )
        builder.add(self.brain)

        self._add_output_processors(builder, tts_engine)

        return builder.build()

    def _add_input_processors(
        self,
        builder: PipelineBuilder,
        registry: ExtensionRegistry,
        asr_engine: ASREngine | None,
        echo_guard_cfg: EchoGuardConfig,
    ) -> None:
        """Add VAD → ASR (with optional speaker ID fan-out) to the pipeline."""
        self._vad_processor: VADProcessor | None = None
        if asr_engine is None:
            return

        from ..audio.input.types import SegmenterConfig
        from ..audio.input.vad import VADEngine

        vad_engine = self._app_context.vad_engine or VADEngine()
        vad_stream = vad_engine.create_stream(cfg=SegmenterConfig(), sample_rate=16000)
        asr_stream = asr_engine.create_stream()

        self._vad_processor = VADProcessor(
            vad_stream=vad_stream,
            bus=self._bus,
            playback_threshold=(
                echo_guard_cfg.vad_threshold_during_playback
                if echo_guard_cfg.enabled
                else None
            ),
        )
        asr_proc = ASRProcessor(asr_stream=asr_stream, bus=self._bus)

        voiceprint_recognizer = self._voiceprint_recognizer
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
        tts_engine: TTSEngine | None,
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
        self._health_monitor = HealthMonitor(
            pipeline=self._pipeline, bus=self._bus, config=self._app_config.health_monitor
        )

    def _init_alerting(self) -> None:
        """Create AlertingObserver and AlertDispatcher from config."""
        acfg = self._app_config.alerting
        self._alerting_observer = AlertingObserver(
            bus=self._bus,
            thresholds=AlertThresholds(
                latency_spike_multiplier=acfg.latency_spike_multiplier,
                latency_spike_consecutive=acfg.latency_spike_consecutive,
                error_rate_threshold=acfg.error_rate_threshold,
                error_rate_window_s=acfg.error_rate_window_s,
                queue_saturation_pct=acfg.queue_saturation_pct,
                queue_saturation_duration_s=acfg.queue_saturation_duration_s,
                stuck_approval_timeout_s=acfg.stuck_approval_timeout_s,
                alert_cooldown_s=acfg.alert_cooldown_s,
            ),
        )

        self._alert_dispatcher = AlertDispatcher(
            bus=self._bus, webhook_url=acfg.webhook_url or None
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_session_id(self, session_id: str) -> None:
        """Resume a specific conversation by ID (legacy compat)."""
        self.brain.resume_conversation(session_id)
        # Phase 18: keep the ToolManager's session in sync so tools
        # opting into ``ToolContext`` (e.g. ChartTool persisting PNGs)
        # see the right session-scoped MediaStore folder.
        self._tool_manager.set_session_id(session_id)

    def resume_conversation(self, conversation_id: str) -> bool:
        """Resume a persisted conversation by its UUID. Returns False if not found."""
        ok = self.brain.resume_conversation(conversation_id)
        if ok:
            self._tool_manager.set_session_id(conversation_id)
        return ok

    def new_conversation(self) -> str:
        """Start a new conversation. Returns new conversation ID."""
        new_id = self.brain.new_conversation()
        self._tool_manager.set_session_id(new_id)
        return new_id

    @property
    def capabilities(self) -> dict[str, bool]:
        """Feature capabilities for the current session."""
        return {
            "asr": self._has_asr,
            "tts": self._has_tts,
            "speaker_id": self._app_config.is_feature_enabled("speaker"),
        }

    @property
    def llm_capabilities(self) -> dict[str, Any]:
        """Input modalities accepted by the configured LLM.

        Resolved once at startup from :mod:`tank_backend.llm.capabilities`.
        Consumers (HTTP upload, web UI) use this to fail fast when the
        user tries to send an unsupported file type.
        """
        return {
            "model_id": self._llm_capabilities.model_id,
            "input_modalities": sorted(self._llm_capabilities.input_modalities),
            "source": self._llm_capabilities.source.value,
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
        self._event_loop = asyncio.get_running_loop()

        if self._title_observer is not None:
            self._title_observer.set_loop(self._event_loop)

        # Wire NotificationHub lifecycle (proactive delivery needs the loop,
        # pipeline, and brain-idle event to schedule injection).
        if self.brain._notification_hub is not None and self._pipeline is not None:
            hub = self.brain._notification_hub
            hub.set_loop(self._event_loop)
            hub.set_pipeline(self._pipeline)
            hub.set_brain_idle_event(self._brain_idle_event)
            hub.set_conversation_id_fn(lambda: self.brain.conversation_id)

        await self._tool_manager.connect_mcp_servers()

        if self._pipeline is not None:
            await self._pipeline.start()

        self._bus_poll_thread = threading.Thread(
            target=self._poll_bus_loop, name="BusPoll", daemon=True
        )
        self._bus_poll_thread.start()

        self._health_monitor.start()

        logger.info("Assistant started")

    async def wait_for_idle(self, timeout: float = 600.0) -> bool:
        """Wait for the brain to finish current work. Returns True if idle."""
        if not self._brain_active:
            return True
        logger.info("Waiting for brain to finish current work (timeout=%.1fs)", timeout)
        try:
            await asyncio.wait_for(self._brain_idle_event.wait(), timeout=timeout)
            logger.info("Brain finished — proceeding with shutdown")
            return True
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for brain to finish (%.1fs)", timeout)
            return False

    async def stop(self) -> None:
        """Stop pipeline and cleanup.

        Waits for the brain to finish its current turn before stopping,
        so in-flight LLM responses and tool executions complete gracefully.
        If the brain doesn't become idle within a reasonable timeout,
        proceed with forced shutdown anyway.
        """
        await self.wait_for_idle(timeout=30.0)

        self.shutdown_signal.stop()

        self._health_monitor.stop()

        if self._pipeline is not None:
            await self._pipeline.stop()

        if self._bus_poll_thread is not None:
            self._bus_poll_thread.join(timeout=2.0)

        await self._tool_manager.cleanup()

        self.brain.close()

        self._event_loop = None

        logger.info("Assistant stopped")

    def push_audio(self, frame: AudioFrame) -> None:
        """Push an audio frame into the pipeline (entry point for mic data)."""
        if self._pipeline is not None:
            self._pipeline.push(frame)

    def process_input(
        self,
        text: str,
        user: str = "Guest",
        *,
        attachments: ContentBlocks | None = None,
    ) -> None:
        """Submit user text input for processing.

        ``attachments`` carries multi-modal blocks (images, documents)
        uploaded via ``POST /api/upload``. They ride on the brain input
        event's metadata so Brain can merge them into the outgoing user
        message as OpenAI content parts alongside the text.
        """
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
                    speaker=user,
                    text=text,
                    is_user=True,
                    is_final=True,
                    msg_id=msg_id,
                ),
            )
        )

        event_metadata: dict[str, Any] = {"msg_id": msg_id}
        if attachments:
            event_metadata["attachments"] = list(attachments)

        if self._pipeline is not None:
            self._pipeline.push_at(
                "brain",
                BrainInputEvent(
                    type=InputType.TEXT,
                    text=text,
                    user=user,
                    language=None,
                    confidence=None,
                    metadata=event_metadata,
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

    def emit_outbound_attachment(
        self,
        blocks: list[Any],
        *,
        msg_id: str | None = None,
        caption: str | None = None,
    ) -> None:
        """Post an ``outbound_attachment`` Bus event.

        Connectors (via :class:`~tank_backend.connectors.manager._ImageDispatcher`)
        subscribe to this event to deliver non-text content — images today,
        other media in later phases — through their platform transports.
        Text replies keep flowing through the usual ``ui_message`` path,
        so nothing about the streaming-text transport changes.

        ``blocks`` should be a list of :class:`ContentBlock` instances; the
        dispatcher filters to the kinds each connector supports. ``msg_id``
        is optional and currently informational — reserved for correlating
        attachments with text streams in a later phase.

        ``caption`` (Phase 15) is an optional human-readable accompaniment.
        When provided, the dispatcher uses it as the ``text`` argument on
        the *first* ``connector.send`` call so the image arrives as
        "image with caption" rather than a bare attachment. Subsequent
        attachments in the same batch go out with no text. Per-platform
        length caps (Telegram 1024, Slack 40 000, Discord 2000) are
        applied by each connector's ``_send_image`` path; passing a
        long caption here is safe.
        """
        if not blocks:
            return
        self._bus.post(
            BusMessage(
                type="outbound_attachment",
                source="assistant",
                payload={
                    "msg_id": msg_id,
                    "blocks": blocks,
                    "caption": caption,
                },
            )
        )

    # ------------------------------------------------------------------
    # Internal event handlers
    # ------------------------------------------------------------------

    def _on_ui_bus_message(self, message: BusMessage) -> None:
        """Forward ui_message bus events to registered callbacks."""
        ui_msg: UIMessage = message.payload
        if isinstance(ui_msg, SignalMessage):
            if ui_msg.signal_type == "processing_started":
                self._brain_active = True
                self._set_brain_idle_event(False)
            elif ui_msg.signal_type == "processing_ended":
                self._brain_active = False
                self._set_brain_idle_event(True)
        for cb in self._ui_callbacks:
            try:
                cb(ui_msg)
            except Exception:
                logger.error("UI callback error", exc_info=True)

    def _on_playback_started(self, _message: BusMessage) -> None:
        self._playback_active = True

    def _on_playback_ended(self, _message: BusMessage) -> None:
        self._playback_active = False

    def _on_title_generated(self, conversation_id: str, title: str) -> None:
        """Sync title into the in-memory conversation to prevent overwrite on next persist."""
        conv = self.brain._context.conversation
        if conv is not None and conv.id == conversation_id:
            conv.title = title

    def _set_brain_idle_event(self, idle: bool) -> None:
        """Thread-safe set/clear of the asyncio brain idle event."""
        loop = self._event_loop
        if loop is not None and loop.is_running():
            if idle:
                loop.call_soon_threadsafe(self._brain_idle_event.set)
            else:
                loop.call_soon_threadsafe(self._brain_idle_event.clear)
        else:
            if idle:
                self._brain_idle_event.set()
            else:
                self._brain_idle_event.clear()

    @property
    def _pipeline_busy(self) -> bool:
        """True when any downstream processor is actively working."""
        return self._brain_active or self._playback_active

    def _on_speech_detected(self, _message: BusMessage) -> None:
        """Handle speech_detected: interrupt pipeline if busy."""
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

    def end_utterance(self) -> None:
        """Force-finalize an in-progress speech segment (push-to-talk send).

        Pushes an ``EndOfUtterance`` sentinel into the VAD queue so it is
        processed on the VAD consumer thread *after* all pending audio frames.
        This avoids racing with the VAD thread over shared state like
        ``_in_speech``. The VAD processor handles the sentinel by calling
        ``VADStream.flush()`` and forwarding the END_SPEECH result downstream
        to ASR.
        """
        if self._vad_processor is None or self._pipeline is None:
            return
        from ..pipeline.processors.vad import END_OF_UTTERANCE
        self._pipeline.push_at("vad", END_OF_UTTERANCE)

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
