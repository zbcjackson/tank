"""Brain — native pipeline Processor for LLM conversation orchestration."""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tiktoken

from ...core.events import (
    AudioOutputRequest,
    BrainInputEvent,
    BrainInterrupted,
    DisplayMessage,
    InputType,
    SignalMessage,
)
from ...observability.trace import generate_trace_id
from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import FlowReturn, Processor
from .echo_guard import EchoGuardConfig, SelfEchoDetector

if TYPE_CHECKING:
    import threading

    from openai.types.chat import ChatCompletionMessageParam

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
    """

    def __init__(
        self,
        llm: "LLM",
        tool_manager: "ToolManager",
        config: BrainConfig,
        bus: Bus,
        interrupt_event: "threading.Event",
        tts_enabled: bool = True,
        echo_guard_config: EchoGuardConfig | None = None,
        llm_summarization: "LLM | None" = None,
        checkpointer: Any = None,
        session_id: str | None = None,
        agent_graph: "AgentGraph | None" = None,
        approval_manager: Any = None,
        memory_service: Any = None,
    ):
        super().__init__(name="brain")
        self._llm = llm
        self._llm_summarization = llm_summarization
        self._tool_manager = tool_manager
        self._config = config
        self._bus = bus
        self._interrupt_event = interrupt_event
        self._tts_enabled = tts_enabled
        self._checkpointer = checkpointer
        self._session_id = session_id
        self._agent_graph = agent_graph
        self._approval_manager = approval_manager
        self._memory_service = memory_service

        # Echo guard — self-echo text detection (Layer 2)
        self._echo_config = echo_guard_config or EchoGuardConfig()
        self._echo_detector = SelfEchoDetector(self._echo_config)

        # Load system prompt from file and append platform context
        self._system_prompt = self._load_system_prompt()
        self._system_prompt += "\n\n" + self._build_platform_context()

        # Initialize conversation history with system prompt as first message
        self._conversation_history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self._system_prompt}
        ]

        # QoS state: when TTS is overloaded, reduce response aggressiveness
        self._qos_skip_tools = False
        self._bus.subscribe("qos", self._on_qos)

    def _load_system_prompt(self) -> str:
        """Load system prompt from file."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "system_prompt.txt"
        try:
            with open(prompt_path, encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.error("System prompt file not found at %s", prompt_path)
            raise
        except Exception as e:
            logger.error("Error loading system prompt: %s", e)
            raise

    @staticmethod
    def _build_platform_context() -> str:
        """Build a platform context block so the LLM knows the user's environment."""
        import os
        import platform

        home = str(Path.home())
        system = platform.system()
        os_label = {
            "Darwin": "macOS",
            "Linux": "Linux",
            "Windows": "Windows",
        }.get(system, system)

        lines = [
            "ENVIRONMENT:",
            f"- Operating system: {os_label}",
            f"- Home directory: {home}",
            f"- Current user: {os.getenv('USER') or os.getenv('USERNAME', 'unknown')}",
        ]

        return "\n".join(lines)

    @property
    def _summarization_llm(self) -> "LLM":
        """LLM used for summarization — dedicated instance or fallback to conversation LLM."""
        return self._llm_summarization or self._llm

    def reset_conversation(self) -> None:
        """Reset conversation history to initial state (system prompt only)."""
        self._conversation_history = [{"role": "system", "content": self._system_prompt}]
        self._checkpoint()
        logger.info("Conversation history reset")

    def set_session_id(self, session_id: str) -> None:
        """Set session ID and load checkpoint if available."""
        self._session_id = session_id
        if self._checkpointer is None:
            return
        try:
            history = self._checkpointer.load(session_id)
            if history:
                self._conversation_history = history
                logger.info(
                    "Loaded checkpoint for session %s (%d messages)",
                    session_id,
                    len(history),
                )
        except Exception:
            logger.error("Failed to load checkpoint for session %s", session_id, exc_info=True)

    def _checkpoint(self) -> None:
        """Persist current conversation history if checkpointer is available."""
        if self._checkpointer is None or self._session_id is None:
            return
        try:
            self._checkpointer.save(self._session_id, self._conversation_history)
        except Exception:
            logger.error("Failed to checkpoint session %s", self._session_id, exc_info=True)

    # ------------------------------------------------------------------
    # Memory helpers
    # ------------------------------------------------------------------

    async def _recall_memory(self, user: str, text: str) -> str:
        """Retrieve relevant memories for a user. Returns formatted string or empty."""
        if self._memory_service is None or not user or user == "Unknown":
            return ""
        try:
            memories = await self._memory_service.recall(user, text)
            if memories:
                return "\n".join(f"- {m}" for m in memories)
        except Exception:
            logger.warning("Memory recall failed for user %s", user, exc_info=True)
        return ""

    def _schedule_memory_store(self, assistant_response: str) -> None:
        """Fire-and-forget: extract and store facts from the turn."""
        import asyncio

        user = getattr(self, "_last_user", None)
        user_text = getattr(self, "_last_user_text", None)
        if self._memory_service is None or not user or user == "Unknown" or not user_text:
            return
        asyncio.create_task(self._store_memory_safe(user, user_text, assistant_response))

    async def _store_memory_safe(
        self, user_id: str, user_msg: str, assistant_msg: str
    ) -> None:
        """Store memory with error isolation — never crashes the pipeline."""
        try:
            await self._memory_service.store_turn(user_id, user_msg, assistant_msg)
        except Exception:
            logger.warning("Memory storage failed for user %s", user_id, exc_info=True)

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        """Process a BrainInputEvent and yield AudioOutputRequest for TTS."""
        event: BrainInputEvent = item

        # Handle system compact before normal processing
        if event.type == InputType.SYSTEM and event.text == "__compact__":
            await self._maybe_compact()
            self._checkpoint()
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
                    session_id=self._session_id,
                )
                if pending:
                    req = pending[0]  # Resolve the oldest pending
                    self._approval_manager.resolve(
                        req.approval_id, approved=intent, reason="voice",
                    )
                    logger.info(
                        "Voice approval: %s → %s for %s",
                        event.text, "approved" if intent else "rejected",
                        req.tool_name,
                    )
                    yield FlowReturn.OK, None
                    return

        self._interrupt_event.clear()

        started_at = time.time()
        logger.info("Brain start processing %s (%s) at %.3f", event.text, event.user, started_at)

        # --- Memory recall (pre-turn) ---
        memory_context = await self._recall_memory(event.user, event.text)

        # Add to history with speaker identity via `name` field
        self._add_to_conversation_history("user", event.text, name=event.user)

        # Capture for post-turn memory storage
        self._last_user = event.user
        self._last_user_text = event.text

        # Generate Assistant Message ID
        assistant_msg_id = f"assistant_{uuid.uuid4().hex[:8]}"
        language = "zh"

        # Generate trace ID for observability linking
        trace_id = generate_trace_id(self._session_id or "unknown")
        self._bus.post(BusMessage(
            type="trace_id",
            source=self.name,
            payload={"trace_id": trace_id, "session_id": self._session_id},
        ))

        # Send processing_started signal
        self._bus.post(BusMessage(
            type="ui_message",
            source=self.name,
            payload=SignalMessage(signal_type="processing_started", msg_id=assistant_msg_id),
        ))

        # Temporarily augment system prompt with memory context
        original_system = self._conversation_history[0]["content"]
        if memory_context:
            self._conversation_history[0] = {
                "role": "system",
                "content": (
                    f"{original_system}\n\n"
                    f"KNOWN FACTS ABOUT {event.user}:\n{memory_context}"
                ),
            }

        try:
            tools = [] if self._qos_skip_tools else self._tool_manager.get_openai_tools()
            if self._qos_skip_tools:
                logger.info("Brain: skipping tools due to QoS feedback")
            audio_request = await self._process_stream(assistant_msg_id, language, tools)

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
            # Restore original system prompt (remove memory augmentation)
            self._conversation_history[0] = {"role": "system", "content": original_system}

            # Always send processing_ended signal
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=SignalMessage(
                    signal_type="processing_ended", msg_id=assistant_msg_id,
                ),
            ))

    async def _process_stream(
        self, msg_id: str, language: str, tools: list[dict[str, Any]]
    ) -> AudioOutputRequest | None:
        """Run the streaming LLM process. Returns AudioOutputRequest or None."""
        if self._agent_graph is not None:
            return await self._process_via_agents(msg_id, language)
        return await self._process_via_llm(msg_id, language, tools)

    async def _process_via_agents(
        self, msg_id: str, language: str
    ) -> AudioOutputRequest | None:
        """Process via AgentGraph — route to specialized agents."""
        from ...agents.base import AgentOutputType, AgentState

        state = AgentState(messages=list(self._conversation_history))
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
                self._add_to_conversation_history("assistant", full_response_text)
                await self._maybe_compact()
                self._checkpoint()
                self._schedule_memory_store(full_response_text)
                if self._tts_enabled:
                    return AudioOutputRequest(content=full_response_text, language=language)

            return None

        except BrainInterrupted:
            # Save what the assistant already said so the LLM has context
            if full_response_text.strip():
                self._add_to_conversation_history("assistant", full_response_text)
                self._checkpoint()
            raise
        except Exception as e:
            logger.error(f"Agent stream processing error: {e}")
            raise
        finally:
            await gen.aclose()

    async def _process_via_llm(
        self, msg_id: str, language: str, tools: list[dict[str, Any]]
    ) -> AudioOutputRequest | None:
        """Run the streaming LLM process directly. Returns AudioOutputRequest or None."""
        full_response_text = ""
        from ...core.events import UpdateType

        gen = self._llm.chat_stream(
            messages=self._conversation_history,
            tools=tools,
            tool_executor=self._tool_manager,
        )
        try:
            async for update_type, content, metadata in gen:
                # Check for interruption
                if self._interrupt_event.is_set():
                    raise BrainInterrupted()

                # Push update to UI via bus
                self._bus.post(BusMessage(
                    type="ui_message",
                    source=self.name,
                    payload=DisplayMessage(
                        speaker="Brain",
                        text=content,
                        is_user=False,
                        msg_id=msg_id,
                        is_final=False,
                        update_type=update_type,
                        metadata=metadata,
                    ),
                ))

                if update_type == UpdateType.TEXT:
                    full_response_text += content

            # Stream ended successfully
            # 1. Finalize UI block
            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=DisplayMessage(
                    speaker="Brain", text="", is_user=False,
                    msg_id=msg_id, is_final=True,
                ),
            ))

            # 2. Add to history
            if full_response_text:
                self._add_to_conversation_history("assistant", full_response_text)

                # 2b. Compact history if over token budget
                await self._maybe_compact()

                # 2c. Persist conversation state
                self._checkpoint()

                # 2d. Store memory (fire-and-forget)
                self._schedule_memory_store(full_response_text)

                # 3. Trigger TTS only when enabled and response is non-empty
                if self._tts_enabled:
                    return AudioOutputRequest(content=full_response_text, language=language)

            return None

        except BrainInterrupted:
            # Save what the assistant already said so the LLM has context
            if full_response_text.strip():
                self._add_to_conversation_history("assistant", full_response_text)
                self._checkpoint()
            raise
        except Exception as e:
            logger.error(f"Stream processing error: {e}")
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

    def _on_qos(self, message: "BusMessage") -> None:
        """Handle QoS feedback from TTS: skip tools when severely overloaded."""
        payload = message.payload or {}
        severity = payload.get("severity", 0.5)
        self._qos_skip_tools = severity > 0.7
        if self._qos_skip_tools:
            logger.info("Brain QoS: skipping tool calls (severity=%.2f)", severity)

    # Shared tiktoken encoder — cl100k_base works for GPT-4/3.5 and is a
    # reasonable approximation for other OpenAI-compatible models.
    _encoder = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, messages: list["ChatCompletionMessageParam"]) -> int:
        """Estimate token count for a list of chat messages."""
        total = 0
        for msg in messages:
            # ~4 tokens overhead per message (role, delimiters)
            total += 4
            content = msg.get("content") or ""
            if isinstance(content, str):
                total += len(self._encoder.encode(content))
        return total

    async def _maybe_compact(self) -> None:
        """Compact conversation history if token count exceeds budget.

        Strategy: try summarization first (preserves context), fall back to
        truncation (drops oldest messages) if summarization fails or there
        aren't enough messages to summarize.
        """
        total_tokens = self._count_tokens(self._conversation_history)
        budget = self._config.max_history_tokens

        if total_tokens <= budget:
            return

        # Keep system prompt (index 0) + last 5 messages
        system_msg = self._conversation_history[0]
        rest = self._conversation_history[1:]

        if len(rest) <= 5:
            # Not enough messages to summarize — go straight to truncation
            self._truncate_history(budget)
            return

        # Try summarization first
        to_summarize = rest[:-5]
        to_keep = rest[-5:]

        summary_prompt = (
            "Summarize the following conversation history concisely. "
            "Preserve key facts, decisions, and context. "
            "Keep it under 500 tokens.\n\n"
        )
        for msg in to_summarize:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            summary_prompt += f"{role}: {content}\n\n"

        try:
            summary_messages = [
                {"role": "system", "content": "You are a helpful assistant that summarizes."},
                {"role": "user", "content": summary_prompt},
            ]
            response = await self._summarization_llm.chat_completion_async(
                messages=summary_messages,
                temperature=0.3,
                max_tokens=500,
            )

            summary_text = response["choices"][0]["message"]["content"]

            summary_msg = {
                "role": "system",
                "content": f"Previous conversation summary: {summary_text}",
            }
            self._conversation_history = [system_msg, summary_msg] + to_keep

            new_tokens = self._count_tokens(self._conversation_history)
            logger.info(
                "History summarized: %d → %d tokens (%d messages → %d)",
                total_tokens,
                new_tokens,
                len(to_summarize) + len(to_keep) + 1,
                len(self._conversation_history),
            )

            self._bus.post(BusMessage(
                type="ui_message",
                source=self.name,
                payload=SignalMessage(
                    signal_type="context_summarized",
                    msg_id="",
                    metadata={
                        "old_tokens": total_tokens,
                        "new_tokens": new_tokens,
                        "messages_summarized": len(to_summarize),
                        "messages_kept": len(to_keep),
                    },
                ),
            ))
        except Exception as e:
            logger.error(f"Summarization failed, falling back to truncation: {e}", exc_info=True)
            self._truncate_history(budget)

    def _truncate_history(self, token_budget: int) -> None:
        """Drop oldest non-system messages to fit within token budget."""
        total_tokens = self._count_tokens(self._conversation_history)
        if total_tokens <= token_budget:
            return

        system_msg = self._conversation_history[0]
        rest = self._conversation_history[1:]

        system_tokens = self._count_tokens([system_msg])
        remaining_budget = token_budget - system_tokens
        keep_from = len(rest)
        running = 0
        for i in range(len(rest) - 1, -1, -1):
            msg_tokens = self._count_tokens([rest[i]])
            if running + msg_tokens > remaining_budget:
                break
            running += msg_tokens
            keep_from = i

        self._conversation_history = [system_msg] + rest[keep_from:]
        new_tokens = self._count_tokens(self._conversation_history)
        logger.info(
            "History truncated: %d → %d tokens (%d messages kept)",
            total_tokens,
            new_tokens,
            len(self._conversation_history),
        )

    def _add_to_conversation_history(
        self, role: str, content: str, *, name: str | None = None
    ) -> None:
        """Append a message to conversation history."""
        msg: dict[str, str] = {"role": role, "content": content}
        if name:
            msg["name"] = name
        self._conversation_history.append(msg)

    def _get_error_message(self, language: str | None) -> str:
        """Get error message in user's language."""
        if language and language.startswith("zh"):
            return "对不起，出现错误，请重试。"
        return "Sorry, an error occurred. Please try again."


def _agent_to_update_type(agent_output_type: Any) -> Any:
    """Map AgentOutputType → UpdateType for bus messages. Returns None for unmapped types."""
    from ...agents.base import AgentOutputType
    from ...core.events import UpdateType

    _MAP = {
        AgentOutputType.TOKEN: UpdateType.TEXT,
        AgentOutputType.THOUGHT: UpdateType.THOUGHT,
        AgentOutputType.TOOL_CALLING: UpdateType.TOOL,
        AgentOutputType.TOOL_EXECUTING: UpdateType.TOOL,
        AgentOutputType.TOOL_RESULT: UpdateType.TOOL,
        AgentOutputType.APPROVAL_NEEDED: UpdateType.APPROVAL,
    }
    return _MAP.get(agent_output_type)


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


def _classify_approval_intent(text: str) -> bool | None:
    """Classify user text as approval (True), rejection (False), or ambiguous (None).

    Uses simple keyword matching. Returns None for ambiguous text,
    which falls through to normal LLM processing.
    """
    normalized = text.strip().lower()
    if not normalized:
        return None

    # Check exact matches and substring matches
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
