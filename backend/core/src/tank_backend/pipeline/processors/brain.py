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
from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import FlowReturn, Processor
from .echo_guard import EchoGuardConfig, SelfEchoDetector

if TYPE_CHECKING:
    import threading

    from openai.types.chat import ChatCompletionMessageParam

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

        # Echo guard — self-echo text detection (Layer 2)
        self._echo_config = echo_guard_config or EchoGuardConfig()
        self._echo_detector = SelfEchoDetector(self._echo_config)

        # Load system prompt from file
        self._system_prompt = self._load_system_prompt()

        # Initialize conversation history with system prompt as first message
        self._conversation_history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self._system_prompt}
        ]

    def _load_system_prompt(self) -> str:
        """Load system prompt from file."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "system_prompt.txt"
        try:
            with open(prompt_path, encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.error(f"System prompt file not found at {prompt_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")
            raise

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

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        """Process a BrainInputEvent and yield AudioOutputRequest for TTS."""
        event: BrainInputEvent = item

        # Handle system reset before normal processing
        if event.type == InputType.SYSTEM and event.text == "__reset__":
            self.reset_conversation()
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

        self._interrupt_event.clear()

        started_at = time.time()
        logger.info("Brain start processing %s (%s) at %.3f", event.text, event.user, started_at)

        # Add to history with speaker context
        user_message = f"{event.user}: {event.text}"
        self._add_to_conversation_history("user", user_message)

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
            tools = self._tool_manager.get_openai_tools()
            audio_request = await self._process_stream(assistant_msg_id, language, tools)

            elapsed = time.time() - started_at
            logger.info("Brain response finished at %.3f, duration_s=%.3f", time.time(), elapsed)

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

    async def _process_stream(
        self, msg_id: str, language: str, tools: list[dict[str, Any]]
    ) -> AudioOutputRequest | None:
        """Run the streaming LLM process. Returns AudioOutputRequest or None."""
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

    def _add_to_conversation_history(self, role: str, content: str) -> None:
        """Append a message to conversation history."""
        self._conversation_history.append({"role": role, "content": content})

    def _get_error_message(self, language: str | None) -> str:
        """Get error message in user's language."""
        if language and language.startswith("zh"):
            return "对不起，出现错误，请重试。"
        return "Sorry, an error occurred. Please try again."
