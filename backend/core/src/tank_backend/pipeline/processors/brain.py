"""Brain — native pipeline Processor for LLM conversation orchestration."""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
from .echo_guard import EchoGuardConfig, SelfEchoDetector

if TYPE_CHECKING:
    import threading

    from ...agents.graph import AgentGraph
    from ...llm.llm import LLM
    from ...tools.manager import ToolManager

logger = logging.getLogger("Brain")


@dataclass(frozen=True)
class BrainConfig:
    """Configuration for the Brain processor (sourced from config.yaml ``brain:`` section)."""

    max_history_tokens: int = 8000


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
        self._approval_manager = approval_manager

        # Register approval notification callback so sub-agent approvals
        # go through the same Bus path as main agent approvals.
        if approval_manager is not None:
            approval_manager.set_on_request(self._on_approval_request)

        # Auto-create a default AgentGraph wrapping the LLM when none provided
        if agent_graph is not None:
            self._agent_graph = agent_graph
        else:
            self._agent_graph = self._create_default_agent_graph()

        # Echo guard — self-echo text detection (Layer 2)
        self._echo_config = echo_guard_config or EchoGuardConfig()
        self._echo_detector = SelfEchoDetector(self._echo_config)

        # Create ContextManager — owns conversation lifecycle, memory, prompt assembly
        from ...context import ContextConfig, ContextManager

        ctx_raw = app_config.get_section("context", {}) if app_config else {}
        context_config = ContextConfig(
            max_history_tokens=config.max_history_tokens,
            store_type=ctx_raw.get("store_type", "file"),
            store_path=ctx_raw.get("store_path", "~/.tank/sessions"),
        )
        self._context = ContextManager(
            app_config=app_config,
            bus=bus,
            config=context_config,
            skill_provider=tool_manager.get_skill_catalog,
        )

        # Start or resume conversation
        self._context.resume_or_new()

        # Track current msg_id for approval notifications from sub-agents
        self._current_msg_id: str = ""

        # QoS state: when TTS is overloaded, reduce response aggressiveness
        self._qos_skip_tools = False
        self._bus.subscribe("qos", self._on_qos)

    def _create_default_agent_graph(self) -> "AgentGraph":
        """Create a default AgentGraph with a single ChatAgent wrapping self._llm."""
        from ...agents.graph import AgentGraph
        from ...agents.llm_agent import LLMAgent

        agent = LLMAgent(
            name="chat",
            llm=self._llm,
            tool_manager=self._tool_manager,
            approval_manager=self._approval_manager,
        )
        return AgentGraph(agents={"chat": agent}, default_agent="chat")

    def reset_conversation(self) -> None:
        """Clear context and start a new conversation."""
        self._context.clear()
        logger.info("Conversation cleared — new: %s", self._context.conversation_id)

    def resume_conversation(self, conversation_id: str) -> bool:
        """Resume a persisted conversation by ID. Returns False if not found."""
        return self._context.resume_conversation(conversation_id)

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

        # --- Voice approval intercept ---
        # When there's a pending approval and user says yes/no, resolve it
        # directly instead of sending to LLM.
        if self._approval_manager is not None:
            intent = _classify_approval_intent(event.text)
            if intent is not None:
                pending = self._approval_manager.get_pending(
                    session_id=self._context.conversation_id,
                )
                if pending:
                    req = pending[0]  # Resolve the oldest pending request
                    self._approval_manager.resolve(req.id, approved=intent)
                    action = "approved" if intent else "rejected"
                    logger.info("Voice approval: %s request %s", action, req.id)
                    yield FlowReturn.OK, None
                    return

        self._interrupt_event.clear()

        started_at = time.time()
        logger.info("Brain start processing %s (%s) at %.3f", event.text, event.user, started_at)

        # --- Memory recall (pre-turn) ---
        await self._context.recall_memory(event.user, event.text)

        # --- Prepare messages for LLM ---
        messages = self._context.prepare_turn(event.user, event.text)

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
    ) -> AudioOutputRequest | None:
        """Process via AgentGraph."""
        from ...agents.base import AgentOutputType, AgentState

        state = AgentState(
            messages=messages,
            metadata={"msg_id": msg_id},
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
                self._context.finish_turn(full_response_text)
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
                self._context.finish_turn(full_response_text)
            raise
        except Exception as e:
            logger.error(f"Agent stream processing error: {e}")
            raise
        finally:
            await gen.aclose()

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

    def _on_approval_request(self, request: Any) -> None:
        """Forward approval request from sub-agent to UI via Bus."""
        self._bus.post(BusMessage(
            type="ui_message",
            source=self.name,
            payload=DisplayMessage(
                speaker="Brain",
                text=request.description,
                is_user=False,
                msg_id=self._current_msg_id,
                is_final=False,
                update_type=UpdateType.APPROVAL_REQUEST,
                metadata={"approval_id": request.id},
            ),
        ))

    @staticmethod
    def _get_error_message(language: str | None) -> str:
        """Get error message in user's language."""
        if language and language.startswith("zh"):
            return "对不起，出现错误，请重试。"
        return "Sorry, an error occurred. Please try again."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_approval_intent(text: str) -> bool | None:
    """Classify user text as approval (True), rejection (False), or neither (None)."""
    return _classify_approval_intent_local(text)


def _agent_to_update_type(agent_output_type: Any) -> UpdateType | None:
    """Map AgentOutputType to UpdateType for UI messages."""
    from ...agents.base import AgentOutputType

    return {
        AgentOutputType.TOKEN: UpdateType.TEXT,
        AgentOutputType.TOOL_CALLING: UpdateType.TOOL,
        AgentOutputType.TOOL_EXECUTING: UpdateType.TOOL,
        AgentOutputType.TOOL_RESULT: UpdateType.TOOL,
    }.get(agent_output_type)


# --- Voice approval intent classification ---

# Keywords that indicate approval (case-insensitive)
_POSITIVE_KEYWORDS = frozenset({
    "yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "proceed",
    "continue", "approve", "do it", "go for it", "confirmed",
    "是", "是的", "好", "好的", "行", "可以", "继续", "执行", "没问题", "确认",
})

# Keywords that indicate rejection
_NEGATIVE_KEYWORDS = frozenset({
    "no", "nope", "cancel", "stop", "don't", "deny", "reject",
    "abort", "never", "negative",
    "不", "不要", "不行", "取消", "停止", "拒绝", "算了", "别",
})


def _classify_approval_intent_local(text: str) -> bool | None:
    """Classify user text as approval (True), rejection (False), or ambiguous (None).

    Uses simple keyword matching. Returns None for ambiguous text,
    which falls through to normal LLM processing.
    """
    normalized = text.strip().lower()
    if not normalized:
        return None

    # Check exact matches
    if normalized in _POSITIVE_KEYWORDS:
        return True
    if normalized in _NEGATIVE_KEYWORDS:
        return False

    # Check if the text starts with a keyword (handles "yes, please" etc.)
    for kw in _POSITIVE_KEYWORDS:
        if normalized.startswith(kw) and (
            len(normalized) == len(kw) or not normalized[len(kw)].isalpha()
        ):
            return True
    for kw in _NEGATIVE_KEYWORDS:
        if normalized.startswith(kw) and (
            len(normalized) == len(kw) or not normalized[len(kw)].isalpha()
        ):
            return False

    return None


def _build_approval_prompt(description: str, language: str) -> str:
    """Build a TTS prompt for approval confirmation."""
    if language and language.startswith("zh"):
        return f"我想要{description}。可以继续吗？"
    return f"I'd like to {description}. Should I proceed?"
