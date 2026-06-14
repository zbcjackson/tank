"""Brain — native pipeline Processor for LLM conversation orchestration."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...config.models import BrainConfig, EchoGuardConfig
from ...core.events import (
    AudioOutputRequest,
    BrainInputEvent,
    BrainInterrupted,
    DisplayMessage,
    InputType,
    SignalMessage,
    UpdateType,
)
from ...observability.trace import generate_trace_id
from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import FlowReturn, Processor
from .echo_guard import SelfEchoDetector

if TYPE_CHECKING:
    import threading

    from ...agents.definition import AgentDefinition
    from ...agents.graph import AgentGraph
    from ...llm.llm import LLM
    from ...tools.manager import ToolManager

logger = logging.getLogger("Brain")

_ACLOSE_TIMEOUT_S = 2.0


class Brain(Processor):
    """The Orchestrator: Process inputs and decide actions.

    Native pipeline Processor that receives BrainInputEvent from the ASR stage
    and yields AudioOutputRequest for the TTS stage downstream.
    UI messages are posted directly to the Bus.

    All conversation context management is delegated to :class:`ContextManager`.
    """

    def __init__(
        self,
        llm: "LLM",
        tool_manager: "ToolManager",
        config: BrainConfig,
        bus: Bus,
        interrupt_event: "threading.Event",
        app_config: Any = None,
        tts_enabled: bool = True,
        echo_guard_config: EchoGuardConfig | None = None,
        agent_graph: "AgentGraph | None" = None,
        approval_manager: Any = None,
        channel_store: Any = None,
        conversation_store: Any = None,
        compaction_store: Any = None,
        messages_store: Any = None,
        media_store: Any = None,
        llm_capabilities: frozenset[str] | None = None,
        worker_store: Any = None,
    ):
        super().__init__(name="brain")
        self._llm = llm
        self._tool_manager = tool_manager
        self._config = config
        self._bus = bus
        self._interrupt_event = interrupt_event
        self._tts_enabled = tts_enabled
        self._worker_store = worker_store
        # NotificationHub replaces WorkerInboxObserver (Phase 3).
        # Set in ``_build_agent_graph`` when WorkerStore is injected.
        self._notification_hub: Any = None

        # --- State-machine approval: PendingToolCallStore ---
        from ...agents.approval import PendingToolCallStore

        self._pending_store = PendingToolCallStore()

        # Register ConfirmActionTool
        from ...tools.confirm_action import ConfirmActionTool

        confirm_tool = ConfirmActionTool(
            pending_store=self._pending_store,
            tool_manager=tool_manager,
            approval_policy=tool_manager.approval_policy,
        )
        tool_manager.register_tool(confirm_tool)

        # Build AgentGraph — use provided one (tests) or build from config
        if agent_graph is not None:
            self._agent_graph = agent_graph
        else:
            self._agent_graph = self._build_agent_graph(app_config)

        # Echo guard — self-echo text detection (Layer 2)
        self._echo_config = echo_guard_config or EchoGuardConfig()
        self._echo_detector = SelfEchoDetector(self._echo_config)

        # Create ConversationResolver — owns conversation lifecycle decisions
        from ...context.resolver import ConversationResolver

        if conversation_store is None:
            # No DB injected (unit tests, stand-alone Brain). Use an
            # in-memory store so the resolver contract holds. Production
            # always injects the unified SqliteConversationStore from
            # api/server.py.
            conversation_store = _InMemoryConversationStore()

        self._resolver = ConversationResolver(
            conversation_store=conversation_store,
            channel_store=channel_store,
        )

        # Create ContextManager — pure context engine, no lifecycle logic
        from ...context import ContextConfig, ContextManager

        context_config = ContextConfig(
            max_history_tokens=config.max_history_tokens if config.max_history_tokens > 0 else 0,
        )
        self._context = ContextManager(
            app_config=app_config,
            resolver=self._resolver,
            bus=bus,
            config=context_config,
            skill_provider=tool_manager.get_skill_catalog,
            media_store=media_store,
            llm_capabilities=llm_capabilities,
            compaction_store=compaction_store,
            messages_store=messages_store,
        )

        # Register preference tool if store is available
        if self._context.preference_store is not None:
            from ...tools.groups import PreferencesToolGroup

            for tool in PreferencesToolGroup(self._context.preference_store).create_tools():
                tool_manager.register_tool(tool)

        # Register context tool so the assistant can compact its own
        # history (with optional focus topic) on user request.
        from ...tools.groups import ConsolidationToolGroup, ContextToolGroup

        for tool in ContextToolGroup(self._context).create_tools():
            tool_manager.register_tool(tool)

        # Register Dream Consolidation tool when enabled in config.
        if app_config is not None:
            for tool in ConsolidationToolGroup(app_config).create_tools():
                tool_manager.register_tool(tool)

        # Start or resume conversation
        system_prompt = self._context.assemble_system_prompt()
        resolved = self._resolver.resume_or_new(system_prompt)
        self._context.set_conversation(resolved)

        # Track current msg_id for approval notifications from sub-agents
        self._current_msg_id: str = ""

        # Guard: only post title-needed once per session
        self._title_requested = False

        # QoS state: when TTS is overloaded, reduce response aggressiveness
        self._qos_skip_tools = False
        self._bus.subscribe("qos", self._on_qos)

    def _build_agent_graph(self, app_config: Any) -> "AgentGraph":
        """Build AgentGraph with a main ChatAgent that has all tools + agent tool."""
        from ...agents.graph import AgentGraph
        from ...agents.llm_agent import LLMAgent

        if app_config is None:
            # Minimal fallback for tests without app_config
            agent = LLMAgent(
                name="chat",
                llm=self._llm,
                tool_manager=self._tool_manager,
                approval_policy=self._tool_manager.approval_policy,
                pending_store=self._pending_store,
                bus=self._bus,
                current_msg_id_fn=lambda: self._current_msg_id,
            )
            self._agent_llm = self._llm
            return AgentGraph(agents={"chat": agent}, default_agent="chat")

        from ...agents.definition import load_agent_definitions
        from ...agents.runner import AgentRunner
        from ...agents.supervisor import WorkerSupervisor
        from ...llm.profile import create_llm_from_profile

        agents_cfg = app_config.agents
        llm_profile = app_config.get_llm_profile(agents_cfg.llm_profile)
        agent_llm = create_llm_from_profile(llm_profile)

        # Load agent definitions from .tank/agents/ directories
        raw_dirs = agents_cfg.dirs
        agent_dirs = [Path(d).expanduser().resolve() for d in raw_dirs]
        definitions = load_agent_definitions(agent_dirs)

        # Create AgentRunner
        runner = AgentRunner(
            llm=agent_llm,
            tool_manager=self._tool_manager,
            bus=self._bus,
            approval_policy=self._tool_manager.approval_policy,
            pending_store=self._pending_store,
            definitions=definitions,
            max_depth=agents_cfg.max_depth,
            max_concurrent=agents_cfg.max_concurrent,
            toolsets_config=app_config.toolsets,
            app_config=app_config,
        )

        # Phase 2: WorkerSupervisor owns dispatch lifecycle. The
        # supervisor is optional — if no WorkerStore was injected
        # (unit tests, stand-alone Brain) we leave it None and
        # AgentTool falls back to the legacy runner-only path.
        worker_supervisor: WorkerSupervisor | None = None
        if self._worker_store is not None:
            # Reap rows left in 'running' from a prior process.
            self._worker_store.reap_running_on_startup()
            worker_supervisor = WorkerSupervisor(
                runner=runner,
                store=self._worker_store,
                bus=self._bus,
                max_depth=agents_cfg.max_depth,
                max_concurrent=agents_cfg.max_concurrent,
            )
            # Phase 3: NotificationHub replaces WorkerInboxObserver.
            # Subscribes to worker + job_delivery events, provides both
            # proactive delivery (timer → inject notification turn) and
            # passive drain (Brain calls drain() at turn start).
            from ...agents.notification_hub import NotificationHub, NotificationHubConfig

            hub_config = NotificationHubConfig()
            if app_config is not None:
                hub_config = getattr(app_config, "notifications", hub_config)
            self._notification_hub = NotificationHub(self._bus, config=hub_config)

        # Register agent tool in ToolManager
        self._tool_manager.set_agent_runner(
            runner, supervisor=worker_supervisor,
        )

        # Register ask_user tool (available to sub-agents only)
        from ...agents.ask_user_tool import AskUserTool

        self._tool_manager.register_tool(AskUserTool())

        # Register agent_reply tool (available to main agent)
        if worker_supervisor is not None and self._worker_store is not None:
            from ...agents.worker_tools import AgentReplyTool

            self._tool_manager.register_tool(
                AgentReplyTool(store=self._worker_store, supervisor=worker_supervisor),
            )

        # Build main agent system prompt with available agent types
        agent_catalog = self._build_agent_catalog(definitions)
        system_prompt = agents_cfg.system_prompt or None
        if system_prompt is None:
            system_prompt = self._build_main_agent_prompt(agent_catalog)

        # Main agent: ALL tools (including agent tool), no exclusions
        # except ask_user which is only for sub-agents
        main_agent = LLMAgent(
            name="chat",
            llm=agent_llm,
            tool_manager=self._tool_manager,
            system_prompt=system_prompt,
            exclude_tools={"ask_user"},
            approval_policy=self._tool_manager.approval_policy,
            pending_store=self._pending_store,
            bus=self._bus,
            current_msg_id_fn=lambda: self._current_msg_id,
        )

        logger.info(
            "AgentGraph built: agent=chat, %d agent definitions loaded",
            len(definitions),
        )
        self._agent_llm = agent_llm
        return AgentGraph(agents={"chat": main_agent}, default_agent="chat")

    @staticmethod
    def _build_agent_catalog(definitions: "dict[str, AgentDefinition]") -> str:
        """Build a compact catalog of available agents for the system prompt."""
        if not definitions:
            return ""
        lines = []
        for defn in definitions.values():
            entry = f"- {defn.name}: {defn.description}"
            lines.append(entry)
        return "\n".join(lines)

    @staticmethod
    def _build_main_agent_prompt(agent_catalog: str) -> str:
        """Build the main agent's system prompt."""
        prompt = (
            "You are the user-facing voice assistant. Your top priority is "
            "to STAY RESPONSIVE — never block the conversation on long work. "
            "You have direct access to file operations, shell commands, web "
            "search, and more.\n\n"

            "## ROUTING DECISION (always do this first)\n\n"
            "Before taking any action, classify the user's request into one "
            "of these routes. State your choice in a brief internal thought "
            "(do NOT speak it aloud), then act:\n\n"
            "1. DIRECT — you can answer or act with 1-2 fast tool calls "
            "   (weather, time, simple file read, quick fact). Do it "
            "   yourself immediately.\n"
            "2. BACKGROUND — the task needs research, multiple steps, "
            "   analysis, web scraping, planning, writing, or any work "
            "   that would take more than ~10 seconds. Dispatch with "
            "   `agent(run_in_background=True)`, tell the user you've "
            "   started it, and stay available.\n"
            "3. SCHEDULED — the user explicitly asks for recurring or "
            "   future-timed work ('every morning', 'daily at 9am', "
            "   'hourly'). Use `manage_jobs`.\n\n"

            "Decision signals:\n"
            "- Multiple web searches needed → BACKGROUND\n"
            "- 'research' / 'analyze' / 'plan' / 'write' / 'compare' → "
            "  BACKGROUND\n"
            "- User says 'in background' / '后台' → BACKGROUND\n"
            "- Single lookup ('what's the weather', 'what time is it') → "
            "  DIRECT\n"
            "- 'every day' / 'hourly' / 'at 9am tomorrow' → SCHEDULED\n"
            "- If unsure, prefer BACKGROUND — the user stays unblocked "
            "  and gets a notification when done.\n\n"

            "## BACKGROUND DISPATCH\n\n"
            "When routing to BACKGROUND:\n"
            "1. Tell the user briefly what you're starting (1 sentence)\n"
            "2. Call `agent(prompt=..., run_in_background=True, "
            "   description=...)`\n"
            "3. Continue the conversation — don't wait for the result\n\n"

            "When the user says 'in background' / '后台' / 'run X for me', "
            "they mean: start X NOW as a background worker. Do NOT create "
            "a scheduled job.\n\n"

            "## SCHEDULED JOBS\n\n"
            "`manage_jobs` is ONLY for RECURRING or SCHEDULED-FOR-LATER "
            "work tied to a specific cron schedule. Never use it just "
            "because the user said 'background'.\n\n"

            "## WHILE WORKERS ARE RUNNING\n\n"
            "The user can keep talking. If they ask:\n"
            "- 'is X done?' / 'status?' → call `agent_status(task_id)`\n"
            "- 'stop X' / 'cancel X' → call `agent_stop(task_id)`\n"
            "- 'what's running?' → call `list_active_agents`\n\n"

            "## WORKER QUESTIONS\n\n"
            "When a worker needs clarification, you will see a notification "
            "like '[Worker ... needs your input: ...]' with a task_id. "
            "Ask the user the question, then call "
            "`agent_reply(task_id, answer)` with their response to resume "
            "the worker.\n\n"

            "## NOTIFICATION TURNS\n\n"
            "When background notifications arrive (worker completions, job "
            "results), you will see them as system messages. Summarize "
            "concisely — this is a voice conversation. Combine multiple "
            "events into one brief update. If a notification isn't relevant "
            "to the current topic, mention it briefly and offer to "
            "elaborate.\n\n"

            "## DIRECT TASKS (EXPLORE / PLAN / ACT)\n\n"
            "For tasks you handle directly:\n"
            "1. EXPLORE: gather info with read-only tools (parallel)\n"
            "2. PLAN: state approach in 1-3 lines\n"
            "3. ACT: execute and deliver\n"
            "For simple requests, skip straight to ACT.\n"
        )
        if agent_catalog:
            prompt += f"\nAvailable agent types:\n{agent_catalog}\n"
        return prompt

    def reset_conversation(self) -> None:
        """Clear context and start a new conversation."""
        system_prompt = self._context.assemble_system_prompt()
        resolved = self._resolver.new(system_prompt)
        self._context.set_conversation(resolved)
        self._pending_store.clear_all()
        logger.info("Conversation cleared — new: %s", self._context.conversation_id)

    def resume_conversation(self, conversation_id: str) -> bool:
        """Resume a persisted conversation by ID. Returns False if not found."""
        system_prompt = self._context.assemble_system_prompt()
        resolved = self._resolver.resume(conversation_id, system_prompt)
        if resolved is None:
            return False
        self._context.set_conversation(resolved)
        # Restore pending approvals from persisted state
        pending_data = self._context.pending_approvals
        if pending_data:
            self._pending_store.restore(pending_data)
            logger.info(
                "Restored %d pending approval(s) from conversation %s",
                len(pending_data),
                conversation_id,
            )
        return True

    def _finish_turn(self, turn_messages: list[dict]) -> None:
        """Finish turn and persist conversation with pending approvals."""
        # Sync pending approvals to conversation before persist
        self._context.pending_approvals = self._pending_store.to_list()
        self._context.finish_turn(turn_messages)
        self._maybe_request_title()

    def _maybe_request_title(self) -> None:
        """Post ``conversation_title_needed`` once per session for untitled conversations.

        The observer wired in ``Assistant`` runs the LLM out-of-band so the
        pipeline never blocks on title generation.
        """
        if self._title_requested:
            return
        conv = self._context.conversation
        if conv is None or conv.title:
            return
        has_user = any(m.get("role") == "user" for m in conv.messages)
        has_assistant = any(m.get("role") == "assistant" for m in conv.messages)
        if not has_user or not has_assistant:
            return
        self._title_requested = True
        self._bus.post(BusMessage(
            type="conversation_title_needed",
            source=self.name,
            payload={"conversation_id": conv.id},
            timestamp=time.time(),
        ))

    # ------------------------------------------------------------------
    # Markdown image extraction
    # ------------------------------------------------------------------

    # Matches ![alt text](url) — standard markdown image syntax.
    # Captures: group(1) = alt text, group(2) = URL.
    _MARKDOWN_IMAGE_RE = __import__("re").compile(
        r"!\[([^\]]*)\]\((https?://[^)]+)\)"
    )

    def _extract_and_emit_markdown_images(
        self, text: str, msg_id: str,
    ) -> str:
        """Scan finalized LLM text for markdown image links and emit them.

        For each ``![alt](url)`` found:
        1. Emit an ``outbound_attachment`` bus event with an
           :class:`ImageBlock` so connectors render the image inline.
        2. Strip the markdown syntax from the text (replace with the
           alt text or empty string) so TTS doesn't read the URL and
           the user sees clean prose.

        Returns the cleaned text with markdown image links removed.
        Only matches ``http(s)://`` URLs — ``media://`` URIs in
        markdown would be unusual (tools use ImageBlock directly).
        """
        from ...core.content import ImageBlock

        matches = list(self._MARKDOWN_IMAGE_RE.finditer(text))
        if not matches:
            return text

        # Emit one outbound_attachment per image found. Each gets its
        # own event so the dispatcher can apply caption-once semantics
        # per the Phase 15 contract.
        for match in matches:
            alt_text = match.group(1).strip()
            url = match.group(2).strip()
            caption = alt_text or None
            try:
                self._bus.post(BusMessage(
                    type="outbound_attachment",
                    source="brain:markdown_image",
                    payload={
                        "msg_id": msg_id,
                        "blocks": [ImageBlock(source=url, mime_type="image/jpeg")],
                        "caption": caption,
                    },
                ))
            except Exception:
                logger.exception(
                    "Failed to emit markdown image attachment (url=%s)", url,
                )

        # Strip the markdown image syntax from the text. Replace with
        # the alt text (if any) so the surrounding prose still reads
        # naturally. E.g. "Here's the chart: ![Q1 Revenue](url)" →
        # "Here's the chart: Q1 Revenue"
        cleaned = self._MARKDOWN_IMAGE_RE.sub(
            lambda m: m.group(1).strip(), text,
        )
        return cleaned

    def new_conversation(self) -> str:
        """Start a fresh conversation. Returns the new conversation ID."""
        self.reset_conversation()
        conv_id = self._context.conversation_id or ""
        self._bus.post(BusMessage(
            type="lifecycle",
            source=self.name,
            payload={"event": "session_start", "session_id": conv_id},
        ))
        return conv_id

    @property
    def conversation_id(self) -> str | None:
        """Current conversation ID."""
        return self._context.conversation_id

    def close(self) -> None:
        """Cleanup — close context manager."""
        self._bus.post(BusMessage(
            type="lifecycle",
            source=self.name,
            payload={
                "event": "session_end",
                "session_id": self._context.conversation_id,
            },
        ))
        self._context.close()

    @property
    def session_id(self) -> str | None:
        """Current session ID."""
        return self._context.conversation_id

    # ------------------------------------------------------------------
    # Pipeline processing
    # ------------------------------------------------------------------

    def _surface_notifications(self) -> None:
        """Inject any queued notifications as synthetic system messages.

        Called at the top of every NORMAL turn. The notifications become
        part of the conversation history so the LLM sees them in the
        very next ``prepare_turn`` call. No-op when no hub is wired
        or no notifications are queued.
        """
        hub = self._notification_hub
        if hub is None:
            return
        conv_id = self._context.conversation_id
        if not conv_id:
            return
        notifications = hub.drain(conv_id)
        if not notifications:
            return
        for notification in notifications:
            self._context.add_message(
                "system", notification.to_system_message(),
            )
        logger.info(
            "Brain: surfaced %d notification(s) for conversation %s",
            len(notifications), conv_id,
        )

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        """Process a BrainInputEvent and yield AudioOutputRequest for TTS."""
        event: BrainInputEvent = item

        # Handle system compact
        if event.type == InputType.SYSTEM and event.text == "__compact__":
            await self._context.compact()
            yield FlowReturn.OK, None
            return

        # Handle notification turn (proactive delivery from NotificationHub)
        if event.type == InputType.SYSTEM and event.text == "__notification__":
            async for result in self._process_notification_turn(event):
                yield result
            return

        if not event.text or not event.text.strip():
            logger.debug(f"Skipping blank text from {event.user}")
            yield FlowReturn.OK, None
            return

        # --- Self-echo text detection (safety net) ---
        if self._echo_config.enabled and self._echo_detector.is_echo(event.text):
            self._bus.post(BusMessage(
                type="echo_discarded",
                source=self.name,
                payload={
                    "reason": "self_echo",
                    "text": event.text,
                },
            ))
            yield FlowReturn.OK, None
            return

        # --- Mode switching: CONFIRMING vs NORMAL ---
        # If there's a pending tool call, switch to CONFIRMING mode
        pending = self._pending_store.get_oldest_pending()
        if pending is not None:
            logger.info("Brain: CONFIRMING mode — pending tool: %s", pending.description)
            self._interrupt_event.clear()
            started_at = time.time()

            # Generate Assistant Message ID
            assistant_msg_id = f"assistant_{uuid.uuid4().hex[:8]}"
            language = "zh"

            # Send processing_started signal
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=SignalMessage(signal_type="processing_started", msg_id=assistant_msg_id),
            ))

            try:
                audio_request = await self._process_confirmation_turn(
                    event, pending, assistant_msg_id, language,
                )

                elapsed = time.time() - started_at
                logger.info("Brain CONFIRMING turn finished: %.3fs", elapsed)

                # Yield AudioOutputRequest for TTS downstream
                if audio_request is not None:
                    self._echo_detector.record_tts(audio_request.content)
                    yield FlowReturn.OK, audio_request
                else:
                    yield FlowReturn.OK, None

            except BrainInterrupted:
                logger.info("Brain: CONFIRMING turn interrupted")
                self._bus.post(BusMessage(
                    type="ui_message",
                    source=self.name,
                    payload=DisplayMessage(
                        speaker="Brain", text="", is_user=False,
                        msg_id=assistant_msg_id, is_final=True,
                    ),
                ))
                yield FlowReturn.OK, None
            except Exception as e:
                logger.error(f"Error in CONFIRMING mode: {e}", exc_info=True)
                error_msg = self._get_error_message(event.language)
                self._bus.post(BusMessage(
                    type="ui_message",
                    source=self.name,
                    payload=DisplayMessage(
                        speaker="Brain",
                        text=error_msg,
                        is_user=False,
                        msg_id=f"brain_err_{uuid.uuid4().hex[:8]}",
                        is_final=True,
                    ),
                ))
                yield FlowReturn.OK, None
            finally:
                # Always send processing_ended signal
                self._bus.post(BusMessage(
                    type="ui_message",
                    source=self.name,
                    payload=SignalMessage(
                        signal_type="processing_ended", msg_id=assistant_msg_id,
                    ),
                ))
            return

        # --- NORMAL mode: proceed with standard agent processing ---

        self._interrupt_event.clear()

        started_at = time.time()
        logger.info("Brain start processing %s (%s) at %.3f", event.text, event.user, started_at)

        # --- Lifecycle hook: turn_start ---
        self._bus.post(BusMessage(
            type="lifecycle",
            source=self.name,
            payload={
                "event": "turn_start",
                "user": event.user,
                "session_id": self._context.conversation_id,
            },
        ))

        # --- Memory recall (pre-turn) ---
        await self._context.recall_memory(event.user, event.text)

        # --- Surface background notifications, if any. Drained
        # ahead of prepare_turn so the synthetic system messages live
        # in conversation history alongside the user's turn.
        self._surface_notifications()

        # --- Prepare messages for LLM ---
        # Multi-modal attachments (images, docs) ride on event metadata;
        # ContextManager handles materialization + OpenAI content-parts.
        attachments = event.metadata.get("attachments") if event.metadata else None
        messages = await self._context.prepare_turn(
            event.user, event.text, attachments=attachments,
        )

        # --- System prompt refresher for mid-turn updates ---
        system_prompt_fn = self._context.get_system_prompt_refresher(user=event.user)

        # Generate Assistant Message ID
        assistant_msg_id = f"assistant_{uuid.uuid4().hex[:8]}"
        language = "zh"

        # Generate trace ID for observability linking
        trace_id = generate_trace_id(self._context.conversation_id or "unknown")
        self._bus.post(BusMessage(
            type="trace_id",
            source=self.name,
            payload={"trace_id": trace_id, "session_id": self._context.conversation_id},
        ))

        # Send processing_started signal
        self._bus.post(BusMessage(
            type="ui_message",
            source=self.name,
            payload=SignalMessage(signal_type="processing_started", msg_id=assistant_msg_id),
        ))

        try:
            audio_request = await self._process_via_agents(
                messages, assistant_msg_id, language, event,
                system_prompt_fn=system_prompt_fn,
            )

            elapsed = time.time() - started_at
            logger.info("Brain response finished at %.3f, duration_s=%.3f", time.time(), elapsed)

            # Reset QoS state after turn completes
            self._qos_skip_tools = False

            # Post LLM latency metric
            self._bus.post(BusMessage(
                type="llm_latency",
                source=self.name,
                payload={
                    "latency_s": elapsed,
                    "user": event.user,
                    "text_length": len(event.text),
                },
            ))

            # --- Lifecycle hook: turn_end ---
            self._bus.post(BusMessage(
                type="lifecycle",
                source=self.name,
                payload={
                    "event": "turn_end",
                    "user": event.user,
                    "session_id": self._context.conversation_id,
                    "latency_s": elapsed,
                },
            ))

            # Yield AudioOutputRequest for TTS downstream
            if audio_request is not None:
                # Record TTS text for self-echo detection
                self._echo_detector.record_tts(audio_request.content)
                yield FlowReturn.OK, audio_request
            else:
                yield FlowReturn.OK, None

        except BrainInterrupted:
            logger.info("Brain: processing interrupted by user speech")
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=DisplayMessage(
                    speaker="Brain", text="", is_user=False,
                    msg_id=assistant_msg_id, is_final=True,
                ),
            ))
            yield FlowReturn.OK, None
        except Exception as e:
            logger.error(f"Error processing input: {e}", exc_info=True)
            error_msg = self._get_error_message(event.language)
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=DisplayMessage(
                    speaker="Brain",
                    text=error_msg,
                    is_user=False,
                    msg_id=f"brain_err_{uuid.uuid4().hex[:8]}",
                    is_final=True,
                ),
            ))
            yield FlowReturn.OK, None
        finally:
            # Always send processing_ended signal
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=SignalMessage(
                    signal_type="processing_ended", msg_id=assistant_msg_id,
                ),
            ))

    async def _process_via_agents(
        self,
        messages: list[dict[str, Any]],
        msg_id: str,
        language: str,
        event: BrainInputEvent,
        system_prompt_fn: Any = None,
    ) -> AudioOutputRequest | None:
        """Process via AgentGraph."""
        from ...agents.base import AgentOutputType, AgentState

        state = AgentState(
            messages=messages,  # type: ignore[arg-type]  # messages is list[dict] at runtime; AgentState accepts broader shapes
            metadata={
                "msg_id": msg_id,
                "system_prompt_fn": system_prompt_fn,
                "user": event.user,
            },
        )
        self._current_msg_id = msg_id
        full_response_text = ""

        assert self._agent_graph is not None
        gen = self._agent_graph.run(state)
        try:
            async for output in gen:
                # Check for interruption
                if self._interrupt_event.is_set():
                    raise BrainInterrupted()

                update_type = _agent_to_update_type(output.type)
                if update_type is None:
                    continue

                self._bus.post(BusMessage(
                    type="ui_message",
                    source=self.name,
                    payload=DisplayMessage(
                        speaker="Brain",
                        text=output.content,
                        is_user=False,
                        msg_id=msg_id,
                        is_final=False,
                        update_type=update_type,
                        metadata=output.metadata,
                    ),
                ))

                if output.type == AgentOutputType.TOKEN:
                    full_response_text += output.content

            # Finalize UI block
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=DisplayMessage(
                    speaker="Brain", text="", is_user=False,
                    msg_id=msg_id, is_final=True,
                ),
            ))

            # Surface the completed reply text to any transport that wants
            # to synthesize voice (e.g. Telegram connector sending a voice
            # message alongside the streamed text). No-op when no subscriber
            # is attached — bus events with no handlers are dropped on next
            # poll.
            #
            # TODO(phase-9+): also emit ``outbound_attachment`` here when the
            # agent layer gains a BLOCK-style output type (e.g. a tool that
            # returns an ImageBlock). Today every AgentOutput.content is a
            # string, so there are no non-text blocks to surface — the
            # ``_ImageDispatcher`` subscriber wired in Phase 4 stays dead
            # until tools can produce ContentBlocks directly.

            # Markdown image extraction: scan the finalized text for
            # ![alt](url) patterns and emit each as an outbound_attachment
            # so connectors render them inline. Strip the markdown syntax
            # from the text so TTS doesn't read it and the user sees clean
            # prose + inline images rather than raw markdown.
            full_response_text = self._extract_and_emit_markdown_images(
                full_response_text, msg_id,
            )

            if full_response_text.strip():
                self._bus.post(BusMessage(
                    type="outbound_voice",
                    source=self.name,
                    payload={
                        "msg_id": msg_id,
                        "text": full_response_text,
                        "language": language,
                    },
                ))

            if full_response_text:
                turn_messages = state.metadata.get("turn_messages", [])
                self._finish_turn(turn_messages)
                await self._context.compact()
                self._context.schedule_memory_store(
                    event.user, event.text, full_response_text,
                )
                if self._tts_enabled:
                    return AudioOutputRequest(content=full_response_text, language=language)

            return None

        except BrainInterrupted:
            # Save what the assistant already said so the LLM has context
            if full_response_text.strip():
                turn_messages = state.metadata.get("turn_messages", [])
                self._finish_turn(turn_messages)
            raise
        except Exception as e:
            logger.error(f"Agent stream processing error: {e}")
            # Phase 19 follow-up: persist whatever turn messages
            # accumulated before the failure. Without this, an LLM
            # error (e.g. provider rejecting a follow-up image) drops
            # the *entire* turn from history — the user sees their
            # request but no chart, no assistant text, nothing. With
            # this, history captures the partial state (tool_call,
            # tool result, follow-up) so resume shows the chart that
            # actually rendered live, and the LLM has context for any
            # subsequent retry. Mirrors the BrainInterrupted branch
            # above.
            turn_messages = state.metadata.get("turn_messages", [])
            if turn_messages:
                try:
                    self._finish_turn(turn_messages)
                except Exception:
                    # Best-effort persistence — if the conversation
                    # store itself is in trouble, propagate the
                    # original error rather than masking it.
                    logger.exception(
                        "Failed to persist partial turn after agent "
                        "stream error",
                    )
            raise
        finally:
            try:
                await asyncio.wait_for(gen.aclose(), timeout=_ACLOSE_TIMEOUT_S)  # type: ignore[attr-defined]  # gen is AsyncGenerator at runtime
            except asyncio.TimeoutError:
                logger.warning("gen.aclose() timed out in _process_via_agents")

    async def _process_confirmation_turn(
        self,
        event: BrainInputEvent,
        pending: Any,
        msg_id: str,
        language: str,
    ) -> AudioOutputRequest | None:
        """Run a CONFIRMING-mode turn with only confirm_action available.

        A lightweight LLMAgent with a focused system prompt classifies the
        user's intent (approve / reject / unclear) and calls confirm_action
        accordingly.  The pipeline never pauses — this is a normal
        Brain.process() → AgentGraph.run() → TTS cycle.
        """
        from ...agents.base import AgentOutputType, AgentState
        from ...agents.graph import AgentGraph
        from ...agents.llm_agent import LLMAgent

        confirmation_prompt = (
            f"There is a pending action that requires user confirmation:\n"
            f"- Tool: {pending.tool_name}\n"
            f"- Action: {pending.description}\n\n"
            "Rules:\n"
            "- If the user clearly approves → call confirm_action(approved=true)\n"
            "- If the user clearly rejects → call confirm_action(approved=false)\n"
            "- If unclear → ask again concisely, do NOT call confirm_action\n"
            "- If user asks about the action → explain briefly, then re-ask\n"
            "- If user changes topic → redirect: "
            "'I have a pending action. Approve or reject first.'\n"
            "- Respond in the user's language\n"
            "- Be concise (this is a voice conversation)\n"
        )

        confirm_agent = LLMAgent(
            name="confirm",
            llm=self._agent_llm,
            tool_manager=self._tool_manager,
            system_prompt=confirmation_prompt,
            tool_filter=["confirm_action"],
            approval_policy=self._tool_manager.approval_policy,
            session_id=self._context.conversation_id or "",
        )

        confirm_graph = AgentGraph(
            agents={"confirm": confirm_agent}, default_agent="confirm",
        )

        messages = await self._context.prepare_turn(event.user, event.text)
        state = AgentState(
            messages=messages,  # type: ignore[arg-type]  # messages is list[dict] at runtime; AgentState accepts broader shapes
            metadata={"msg_id": msg_id, "user": event.user},
        )
        self._current_msg_id = msg_id
        full_response_text = ""

        gen = confirm_graph.run(state)
        tool_executed = False
        try:
            async for output in gen:
                # Only allow interrupts BEFORE the tool has executed.
                # Once confirm_action consumes + executes the pending call,
                # interrupting would lose the result with no way to recover
                # (the pending call is already gone from the store).
                if not tool_executed and self._interrupt_event.is_set():
                    raise BrainInterrupted()

                # Track when confirm_action finishes executing
                if output.type == AgentOutputType.TOOL_RESULT:
                    tool_executed = True

                update_type = _agent_to_update_type(output.type)
                if update_type is None:
                    continue

                self._bus.post(BusMessage(
                    type="ui_message",
                    source=self.name,
                    payload=DisplayMessage(
                        speaker="Brain",
                        text=output.content,
                        is_user=False,
                        msg_id=msg_id,
                        is_final=False,
                        update_type=update_type,
                        metadata=output.metadata,
                    ),
                ))

                if output.type == AgentOutputType.TOKEN:
                    full_response_text += output.content

            # Finalize UI block
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=DisplayMessage(
                    speaker="Brain", text="", is_user=False,
                    msg_id=msg_id, is_final=True,
                ),
            ))

            if full_response_text:
                turn_messages = state.metadata.get("turn_messages", [])
                self._finish_turn(turn_messages)
                if self._tts_enabled:
                    return AudioOutputRequest(
                        content=full_response_text, language=language,
                    )

            return None

        except BrainInterrupted:
            if full_response_text.strip():
                turn_messages = state.metadata.get("turn_messages", [])
                self._finish_turn(turn_messages)
            raise
        except Exception as e:
            logger.error(f"Confirmation turn error: {e}")
            # Same partial-persist policy as the main agent stream
            # error path above — see that branch for rationale.
            turn_messages = state.metadata.get("turn_messages", [])
            if turn_messages:
                try:
                    self._finish_turn(turn_messages)
                except Exception:
                    logger.exception(
                        "Failed to persist partial confirmation turn",
                    )
            raise
        finally:
            try:
                await asyncio.wait_for(gen.aclose(), timeout=_ACLOSE_TIMEOUT_S)  # type: ignore[attr-defined]  # gen is AsyncGenerator at runtime
            except asyncio.TimeoutError:
                logger.warning("gen.aclose() timed out in _process_confirmation_turn")

    def handle_event(self, event: PipelineEvent) -> bool:
        """Handle pipeline events (interrupt, flush)."""
        if event.type == "interrupt":
            self._interrupt_event.set()
            return False  # propagate to other processors
        if event.type == "flush":
            return False  # propagate
        return False

    async def _process_notification_turn(
        self, event: BrainInputEvent,
    ) -> AsyncIterator[tuple[FlowReturn, Any]]:
        """Run a proactive notification turn triggered by NotificationHub.

        Drains queued notifications, injects them as system messages,
        then runs the main ChatAgent so it can summarize/report to the user.

        The target conversation_id comes from the event metadata (set by
        NotificationHub when it injected the event). This ensures
        notifications are drained from the correct queue even if the user
        switched conversations between dispatch and delivery.
        """
        if self._notification_hub is None:
            yield FlowReturn.OK, None
            return

        # Use the conversation_id from the injected event metadata,
        # falling back to the current conversation if not specified.
        target_conv_id = (
            (event.metadata or {}).get("conversation_id")
            or self._context.conversation_id
        )
        if not target_conv_id:
            yield FlowReturn.OK, None
            return

        notifications = self._notification_hub.drain(target_conv_id)
        if not notifications:
            yield FlowReturn.OK, None
            return

        self._interrupt_event.clear()
        started_at = time.time()

        # Inject notifications as system messages
        combined = "\n".join(n.to_system_message() for n in notifications)
        self._context.add_message(
            "system",
            f"[{len(notifications)} background event(s). "
            f"Summarize the key findings for the user.]\n"
            f"{combined}",
        )

        logger.info(
            "Brain: notification turn with %d event(s) for %s",
            len(notifications), target_conv_id,
        )

        # Get current messages for LLM without adding a synthetic user message.
        # The notifications are already injected as system messages above.
        messages = list(self._context.messages)

        assistant_msg_id = f"assistant_{uuid.uuid4().hex[:8]}"
        language = "zh"

        # Send processing_started signal
        self._bus.post(BusMessage(
            type="ui_message",
            source=self.name,
            payload=SignalMessage(signal_type="processing_started", msg_id=assistant_msg_id),
        ))

        try:
            audio_request = await self._process_via_agents(
                messages, assistant_msg_id, language, event,
            )

            elapsed = time.time() - started_at
            logger.info("Brain notification turn finished: %.3fs", elapsed)

            if audio_request is not None:
                self._echo_detector.record_tts(audio_request.content)
                yield FlowReturn.OK, audio_request
            else:
                yield FlowReturn.OK, None

        except BrainInterrupted:
            logger.info("Brain: notification turn interrupted")
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=DisplayMessage(
                    speaker="Brain", text="", is_user=False,
                    msg_id=assistant_msg_id, is_final=True,
                ),
            ))
            yield FlowReturn.OK, None
        except Exception as e:
            logger.error(f"Error in notification turn: {e}", exc_info=True)
            yield FlowReturn.OK, None
        finally:
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=SignalMessage(
                    signal_type="processing_ended", msg_id=assistant_msg_id,
                ),
            ))

    def _on_qos(self, message: BusMessage) -> None:
        """Handle QoS feedback from TTS/playback."""
        payload = message.payload or {}
        severity = payload.get("severity", 0)
        if severity >= 0.5:
            self._qos_skip_tools = True
            logger.info("Brain QoS: skipping tool calls (severity=%.2f)", severity)

    @staticmethod
    def _get_error_message(language: str | None) -> str:
        """Get error message in user's language."""
        if language and language.startswith("zh"):
            return "对不起，出现错误，请重试。"
        return "Sorry, an error occurred. Please try again."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_to_update_type(agent_output_type: Any) -> UpdateType | None:
    """Map AgentOutputType to UpdateType for UI messages."""
    from ...agents.base import AgentOutputType

    return {
        AgentOutputType.TOKEN: UpdateType.TEXT,
        AgentOutputType.TOOL_CALLING: UpdateType.TOOL,
        AgentOutputType.TOOL_EXECUTING: UpdateType.TOOL,
        AgentOutputType.TOOL_RESULT: UpdateType.TOOL,
    }.get(agent_output_type)


class _InMemoryConversationStore:
    """Ephemeral ConversationStore used when Brain is built without a DB.

    Production paths inject :class:`SqliteConversationStore` via
    ``api/server.py``. This stand-in only exists so unit tests that
    construct Brain directly still have a functioning resolver.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._order: list[str] = []

    def save(self, conversation: Any) -> None:
        if conversation.id not in self._data:
            self._order.append(conversation.id)
        self._data[conversation.id] = conversation

    def load(self, conversation_id: str) -> Any:
        return self._data.get(conversation_id)

    def list_conversations(self) -> list:
        return []

    def delete(self, conversation_id: str) -> None:
        self._data.pop(conversation_id, None)
        if conversation_id in self._order:
            self._order.remove(conversation_id)

    def find_latest(self) -> Any:
        if not self._order:
            return None
        return self._data[self._order[-1]]

    def close(self) -> None:
        return
