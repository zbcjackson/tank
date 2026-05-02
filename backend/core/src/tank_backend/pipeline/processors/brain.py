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
    ):
        super().__init__(name="brain")
        self._llm = llm
        self._tool_manager = tool_manager
        self._config = config
        self._bus = bus
        self._interrupt_event = interrupt_event
        self._tts_enabled = tts_enabled

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

        # Create ContextManager — owns conversation lifecycle, memory, prompt assembly
        from ...context import ContextConfig, ContextManager

        context_config = ContextConfig(
            max_history_tokens=config.max_history_tokens,
            store_type=app_config.context.store_type if app_config else "file",
            store_path=app_config.context.store_path if app_config else "~/.tank/sessions",
        )
        self._context = ContextManager(
            app_config=app_config,
            bus=bus,
            config=context_config,
            skill_provider=tool_manager.get_skill_catalog,
        )

        # Register preference tool if store is available
        if self._context.preference_store is not None:
            from ...tools.groups import PreferencesToolGroup

            for tool in PreferencesToolGroup(self._context.preference_store).create_tools():
                tool_manager.register_tool(tool)

        # Start or resume conversation
        self._context.resume_or_new()

        # Track current msg_id for approval notifications from sub-agents
        self._current_msg_id: str = ""

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
        from ...llm.profile import create_llm_from_profile

        agents_cfg = app_config.agents
        llm_profile_name = agents_cfg.llm_profile

        try:
            llm_profile = app_config.get_llm_profile(llm_profile_name)
            agent_llm = create_llm_from_profile(llm_profile)
        except (KeyError, ValueError):
            logger.warning(
                "Agent references unknown LLM profile %r — using Brain's LLM",
                llm_profile_name,
            )
            agent_llm = self._llm

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
        )

        # Register agent tool in ToolManager
        self._tool_manager.set_agent_runner(runner)

        # Build main agent system prompt with available agent types
        agent_catalog = self._build_agent_catalog(definitions)
        system_prompt = agents_cfg.system_prompt or None
        if system_prompt is None:
            system_prompt = self._build_main_agent_prompt(agent_catalog)

        # Main agent: ALL tools (including agent tool), no exclusions
        main_agent = LLMAgent(
            name="chat",
            llm=agent_llm,
            tool_manager=self._tool_manager,
            system_prompt=system_prompt,
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
    def _build_agent_catalog(definitions: dict[str, object]) -> str:
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

    def reset_conversation(self) -> None:
        """Clear context and start a new conversation."""
        self._context.clear()
        self._pending_store.clear_all()
        logger.info("Conversation cleared — new: %s", self._context.conversation_id)

    def resume_conversation(self, conversation_id: str) -> bool:
        """Resume a persisted conversation by ID. Returns False if not found."""
        success = self._context.resume_conversation(conversation_id)
        if success:
            # Restore pending approvals from persisted state
            pending_data = self._context.pending_approvals
            if pending_data:
                self._pending_store.restore(pending_data)
                logger.info(
                    "Restored %d pending approval(s) from conversation %s",
                    len(pending_data),
                    conversation_id,
                )
        return success

    def _finish_turn(self, turn_messages: list[dict]) -> None:
        """Finish turn and persist conversation with pending approvals."""
        # Sync pending approvals to conversation before persist
        self._context.pending_approvals = self._pending_store.to_list()
        self._context.finish_turn(turn_messages)

    def new_conversation(self) -> str:
        """Start a fresh conversation. Returns the new conversation ID."""
        self._context.clear()
        return self._context.conversation_id or ""

    @property
    def conversation_id(self) -> str | None:
        """Current conversation ID."""
        return self._context.conversation_id

    def close(self) -> None:
        """Cleanup — close context manager."""
        self._context.close()

    @property
    def session_id(self) -> str | None:
        """Current session ID."""
        return self._context.conversation_id

    # ------------------------------------------------------------------
    # Pipeline processing
    # ------------------------------------------------------------------

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        """Process a BrainInputEvent and yield AudioOutputRequest for TTS."""
        event: BrainInputEvent = item

        # Handle system compact
        if event.type == InputType.SYSTEM and event.text == "__compact__":
            await self._context.compact()
            yield FlowReturn.OK, None
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

        # --- Memory recall (pre-turn) ---
        await self._context.recall_memory(event.user, event.text)

        # --- Prepare messages for LLM ---
        messages = self._context.prepare_turn(event.user, event.text)

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
            messages=messages,
            metadata={
                "msg_id": msg_id,
                "system_prompt_fn": system_prompt_fn,
                "user": event.user,
            },
        )
        self._current_msg_id = msg_id
        full_response_text = ""

        gen = self._agent_graph.run(state)  # type: ignore[union-attr]
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
            raise
        finally:
            try:
                await asyncio.wait_for(gen.aclose(), timeout=_ACLOSE_TIMEOUT_S)
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

        messages = self._context.prepare_turn(event.user, event.text)
        state = AgentState(
            messages=messages,
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
            raise
        finally:
            try:
                await asyncio.wait_for(gen.aclose(), timeout=_ACLOSE_TIMEOUT_S)
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
