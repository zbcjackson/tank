import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING, Dict, Any

from .events import AudioOutputRequest, BrainInputEvent, BrainInterrupted, DisplayMessage, UpdateType, SignalMessage
from .runtime import RuntimeContext
from .shutdown import StopSignal
from .worker import QueueWorker
from ..audio.output import AudioOutput
from ..config.settings import VoiceAssistantConfig

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
        speaker_ref: AudioOutput,
        llm: "LLM",
        tool_manager: "ToolManager",
        config: VoiceAssistantConfig,
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
        
        # Load system prompt from file
        self._system_prompt = self._load_system_prompt()
        
        # Initialize conversation history with system prompt as first message
        self._conversation_history: List["ChatCompletionMessageParam"] = [
            {"role": "system", "content": self._system_prompt}
        ]
        
        # Event loop for async operations (created by base class)
        # Alias to base class _loop for backward compatibility
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
    
    def _load_system_prompt(self) -> str:
        """Load system prompt from file."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
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
        """Cleanup event loop and clear alias."""
        super()._teardown_event_loop()
        self._event_loop = None

    def handle(self, event: BrainInputEvent) -> None:
        """
        Handles inputs from both Keyboard and Perception.
        """
        if not event.text or not event.text.strip():
            logger.debug(f"Skipping blank text from {event.user}")
            return

        if self._runtime.interrupt_event is not None:
            self._runtime.interrupt_event.clear()

        started_at = time.time()
        logger.info("Brain processing started for input at %.3f", started_at)

        # Add to history
        self._add_to_conversation_history("user", event.text)

        # 3. Generate Assistant Message ID
        assistant_msg_id = f"assistant_{uuid.uuid4().hex[:8]}"
        language = "zh"

        # Send processing_started signal
        self._runtime.ui_queue.put(
            SignalMessage(
                signal_type="processing_started",
                msg_id=assistant_msg_id
            )
        )

        try:
            tools = self._tool_manager.get_openai_tools()
            self._process_stream(assistant_msg_id, language, tools)

            ended_at = time.time()
            logger.info("Brain response finished at %.3f, duration_s=%.3f", ended_at, ended_at - started_at)

        except BrainInterrupted:
            logger.info("Brain: processing interrupted by user speech")
            # Mark the current assistant block as final/stopped
            self._runtime.ui_queue.put(
                DisplayMessage(
                    speaker="Brain",
                    text="",
                    is_user=False,
                    msg_id=assistant_msg_id,
                    is_final=True
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
                    is_final=True
                )
            )
        finally:
            # Always send processing_ended signal
            self._runtime.ui_queue.put(
                SignalMessage(
                    signal_type="processing_ended",
                    msg_id=assistant_msg_id
                )
            )

    def _process_stream(self, msg_id: str, language: str, tools: List[Dict[str, Any]]) -> None:
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
                    # Check for interruption
                    if self._config.speech_interrupt_enabled and self._runtime.interrupt_event.is_set():
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
                            metadata=metadata
                        )
                    )

                    if update_type == UpdateType.TEXT:
                        full_response_text += content

                # Stream ended successfully
                # 1. Finalize UI block
                self._runtime.ui_queue.put(
                    DisplayMessage(
                        speaker="Brain",
                        text="",
                        is_user=False,
                        msg_id=msg_id,
                        is_final=True
                    )
                )

                # 2. Add to history
                if full_response_text:
                    self._add_to_conversation_history("assistant", full_response_text)

                    # 3. Trigger TTS only after full response is generated
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

        self._event_loop.run_until_complete(stream_task())

    def _add_to_conversation_history(self, role: str, content: str) -> None:
        """Add message to conversation history and enforce limit."""
        self._conversation_history.append({"role": role, "content": content})
        
        # Limit: keep system (index 0) + last max_conversation_history * 2 messages
        # (each conversation turn = 1 user + 1 assistant = 2 messages)
        max_messages = self._config.max_conversation_history * 2 + 1
        if len(self._conversation_history) > max_messages:
            self._conversation_history = (
                [self._conversation_history[0]] +  # Keep system prompt
                self._conversation_history[-(max_messages - 1):]  # Keep last N messages
            )
    
    def _get_error_message(self, language: Optional[str]) -> str:
        """Get error message in user's language."""
        if language and language.startswith("zh"):
            return "对不起，出现错误，请重试。"
        return "Sorry, an error occurred. Please try again."
