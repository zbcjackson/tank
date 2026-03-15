import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tiktoken

from ..audio.output import AudioOutput
from ..config.settings import VoiceAssistantConfig
from .events import (
    AudioOutputRequest,
    BrainInputEvent,
    BrainInterrupted,
    DisplayMessage,
    InputType,
    SignalMessage,
)
from .runtime import RuntimeContext
from .shutdown import StopSignal
from .worker import QueueWorker

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

    from ..llm.llm import LLM
    from ..tools.manager import ToolManager

logger = logging.getLogger("Brain")


class Brain(QueueWorker[BrainInputEvent]):
    """
    The Orchestrator: Process inputs and decide actions.

    Consumes BrainInputEvent from brain_input_queue and processes them using LLM.
    """

    def __init__(
        self,
        shutdown_signal: StopSignal,
        runtime: RuntimeContext,
        speaker_ref: "AudioOutput | None",
        llm: "LLM",
        tool_manager: "ToolManager",
        config: VoiceAssistantConfig,
        tts_enabled: bool = True,
    ):
        super().__init__(
            name="BrainThread",
            stop_signal=shutdown_signal,
            input_queue=runtime.brain_input_queue,
            poll_interval_s=0.1,
        )
        self._runtime = runtime
        self.speaker = speaker_ref
        self._llm = llm
        self._tool_manager = tool_manager
        self._config = config
        self._tts_enabled = tts_enabled

        # Load system prompt from file
        self._system_prompt = self._load_system_prompt()

        # Initialize conversation history with system prompt as first message
        self._conversation_history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self._system_prompt}
        ]

        # Event loop for async operations (created by base class)
        # Alias to base class _loop for backward compatibility
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def _load_system_prompt(self) -> str:
        """Load system prompt from file."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
        try:
            with open(prompt_path, encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.error(f"System prompt file not found at {prompt_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")
            raise

    def _setup_event_loop(self) -> asyncio.AbstractEventLoop:
        """Create event loop for async LLM operations."""
        loop = asyncio.new_event_loop()
        # Set alias for backward compatibility with existing code that uses self._event_loop
        self._event_loop = loop
        return loop

    def _teardown_event_loop(self) -> None:
        """Close all async generators and pending tasks before closing the loop."""
        if self._loop is not None:
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                pending = asyncio.all_tasks(self._loop)
                if pending:
                    for task in pending:
                        task.cancel()
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                self._loop.close()
        self._event_loop = None
        self._loop = None

    def reset_conversation(self) -> None:
        """Reset conversation history to initial state (system prompt only)."""
        self._conversation_history = [{"role": "system", "content": self._system_prompt}]
        logger.info("Conversation history reset")

    def handle(self, event: BrainInputEvent) -> None:
        """
        Handles inputs from both Keyboard and Perception.
        """
        # Handle system reset before normal processing
        if event.type == InputType.SYSTEM and event.text == "__reset__":
            self.reset_conversation()
            return

        if not event.text or not event.text.strip():
            logger.debug(f"Skipping blank text from {event.user}")
            return

        if self._runtime.interrupt_event is not None:
            self._runtime.interrupt_event.clear()

        started_at = time.time()
        logger.info("Brain processing started for input at %.3f", started_at)

        # Add to history with speaker context
        user_message = f"{event.user}: {event.text}"
        self._add_to_conversation_history("user", user_message)

        # 3. Generate Assistant Message ID
        assistant_msg_id = f"assistant_{uuid.uuid4().hex[:8]}"
        language = "zh"

        # Send processing_started signal
        self._runtime.ui_queue.put(
            SignalMessage(signal_type="processing_started", msg_id=assistant_msg_id)
        )

        try:
            tools = self._tool_manager.get_openai_tools()
            self._process_stream(assistant_msg_id, language, tools)

            ended_at = time.time()
            logger.info(
                "Brain response finished at %.3f, duration_s=%.3f", ended_at, ended_at - started_at
            )

        except BrainInterrupted:
            logger.info("Brain: processing interrupted by user speech")
            # Mark the current assistant block as final/stopped
            self._runtime.ui_queue.put(
                DisplayMessage(
                    speaker="Brain", text="", is_user=False, msg_id=assistant_msg_id, is_final=True
                )
            )
        except Exception as e:
            logger.error(f"Error processing input: {e}", exc_info=True)
            error_msg = self._get_error_message(event.language)
            self._runtime.ui_queue.put(
                DisplayMessage(
                    speaker="Brain",
                    text=error_msg,
                    is_user=False,
                    msg_id=f"brain_err_{uuid.uuid4().hex[:8]}",
                    is_final=True,
                )
            )
        finally:
            # Always send processing_ended signal
            self._runtime.ui_queue.put(
                SignalMessage(signal_type="processing_ended", msg_id=assistant_msg_id)
            )

    def _process_stream(self, msg_id: str, language: str, tools: list[dict[str, Any]]) -> None:
        """Run the streaming LLM process in the event loop."""
        if self._event_loop is None:
            raise RuntimeError("Event loop not initialized")

        async def stream_task():
            full_response_text = ""
            from ..core.events import UpdateType

            gen = self._llm.chat_stream(
                messages=self._conversation_history,
                tools=tools,
                tool_executor=self._tool_manager,
            )
            try:
                async for update_type, content, metadata in gen:
                    # Exit cleanly on shutdown
                    if self._stop_signal.is_set():
                        return
                    # Check for interruption
                    if (
                        self._config.speech_interrupt_enabled
                        and self._runtime.interrupt_event.is_set()
                    ):
                        raise BrainInterrupted()

                    # Push update to UI
                    self._runtime.ui_queue.put(
                        DisplayMessage(
                            speaker="Brain",
                            text=content,
                            is_user=False,
                            msg_id=msg_id,
                            is_final=False,
                            update_type=update_type,
                            metadata=metadata,
                        )
                    )

                    if update_type == UpdateType.TEXT:
                        full_response_text += content

                # Stream ended successfully
                # 1. Finalize UI block
                self._runtime.ui_queue.put(
                    DisplayMessage(
                        speaker="Brain", text="", is_user=False, msg_id=msg_id, is_final=True
                    )
                )

                # 2. Add to history
                if full_response_text:
                    self._add_to_conversation_history("assistant", full_response_text)

                    # 2b. Summarize old history if over threshold
                    await self._maybe_summarize()

                    # 3. Trigger TTS only when enabled and response is non-empty
                    if self._tts_enabled:
                        self._runtime.audio_output_queue.put(
                            AudioOutputRequest(content=full_response_text, language=language)
                        )

            except BrainInterrupted:
                raise
            except Exception as e:
                logger.error(f"Stream processing error: {e}")
                raise
            finally:
                await gen.aclose()

        self._run_async(stream_task())

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

    async def _maybe_summarize(self) -> None:
        """Summarize old conversation history if token count exceeds threshold."""
        total_tokens = self._count_tokens(self._conversation_history)
        threshold = self._config.summarize_at_tokens

        if total_tokens <= threshold:
            return

        # Keep system prompt (index 0) + last 5 messages
        system_msg = self._conversation_history[0]
        rest = self._conversation_history[1:]

        if len(rest) <= 5:
            # Not enough messages to summarize
            return

        # Summarize everything except system + last 5
        to_summarize = rest[:-5]
        to_keep = rest[-5:]

        # Build summarization prompt
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
            # Call LLM with low temperature for factual summary
            summary_messages = [
                {"role": "system", "content": "You are a helpful assistant that summarizes."},
                {"role": "user", "content": summary_prompt},
            ]
            response = await self._llm.chat_completion_async(
                messages=summary_messages,
                temperature=0.3,
                max_tokens=500,
            )

            summary_text = response["choices"][0]["message"]["content"]

            # Replace old messages with summary
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

            # Post summarization metric to UI queue (forwarded to bus by BrainProcessor)
            self._runtime.ui_queue.put(
                SignalMessage(
                    signal_type="context_summarized",
                    msg_id="",
                    metadata={
                        "old_tokens": total_tokens,
                        "new_tokens": new_tokens,
                        "messages_summarized": len(to_summarize),
                        "messages_kept": len(to_keep),
                    },
                )
            )
        except Exception as e:
            logger.error(f"Summarization failed: {e}", exc_info=True)
            # Fall back to truncation if summarization fails
            pass

    def _add_to_conversation_history(self, role: str, content: str) -> None:
        """Add message to conversation history and enforce token budget."""
        self._conversation_history.append({"role": role, "content": content})

        token_budget = self._config.max_history_tokens
        total_tokens = self._count_tokens(self._conversation_history)

        if total_tokens <= token_budget:
            return

        # Always keep system prompt (index 0); drop oldest non-system messages first
        system_msg = self._conversation_history[0]
        rest = self._conversation_history[1:]

        # Walk backwards from most recent, accumulating tokens until budget is hit
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

    def _get_error_message(self, language: str | None) -> str:
        """Get error message in user's language."""
        if language and language.startswith("zh"):
            return "对不起，出现错误，请重试。"
        return "Sorry, an error occurred. Please try again."
