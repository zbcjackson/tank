import asyncio
import logging
import time
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING, Dict, Any

from .events import AudioOutputRequest, BrainInputEvent, DisplayMessage
from .runtime import RuntimeContext
from .shutdown import StopSignal
from .worker import QueueWorker
from ..audio.output import SpeakerHandler
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
        speaker_ref: SpeakerHandler,
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
        
        # Event loop for async operations (created in run())
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

    def run(self) -> None:
        """Create event loop for this thread and run queue worker."""
        # Create event loop for this thread
        self._event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._event_loop)
        try:
            super().run()
        finally:
            # Close event loop when thread stops
            if self._event_loop:
                self._event_loop.close()

    def handle(self, event: BrainInputEvent) -> None:
        """
        Handles inputs from both Keyboard and Perception.
        
        Processes BrainInputEvent by:
        1. Filtering blank text
        2. Adding user message to conversation history
        3. Calling LLM with conversation history
        4. Adding assistant response to history
        5. Outputting to display and audio queues
        """
        # Filter blank text (defensive check)
        if not event.text or not event.text.strip():
            logger.debug(f"Skipping blank text from {event.user}")
            return

        started_at = time.time()
        logger.info("Brain processing started for input at %.3f", started_at)

        # Add user message to conversation history
        self._add_to_conversation_history("user", event.text)

        try:
            # Call LLM with conversation history (already includes system prompt)
            tools = self._tool_manager.get_openai_tools()
            response = self._call_llm_async(self._conversation_history, tools)
            
            # Extract content from response
            message = response["choices"][0]["message"]
            content = message.get("content", "")
            
            if not content:
                logger.warning("LLM returned empty content")
                error_msg = self._get_error_message(event.language)
                self._runtime.display_queue.put(
                    DisplayMessage(speaker="Brain", text=error_msg)
                )
                return
            
            # Add assistant response to conversation history
            self._add_to_conversation_history("assistant", content)

            # Log tool iterations if any occurred
            if response.get("tool_iterations", 0) > 1:
                logger.info(f"Completed response after {response['tool_iterations']} tool iterations")

            ended_at = time.time()
            duration_s = ended_at - started_at
            logger.info("Brain response ready at %.3f, duration_s=%.3f", ended_at, duration_s)

            # Send response to UI and Speaker
            self._runtime.display_queue.put(
                DisplayMessage(speaker="Brain", text=content)
            )
            language = (event.language or "auto").strip() or "auto"
            self._runtime.audio_output_queue.put(
                AudioOutputRequest(content=content, language=language)
            )
            
        except Exception as e:
            logger.error(f"Error processing input: {e}", exc_info=True)
            # Don't update conversation history on error
            # User message was already added, but we'll leave it for retry
            error_msg = self._get_error_message(event.language)
            self._runtime.display_queue.put(
                DisplayMessage(speaker="Brain", text=error_msg)
            )
    
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
    
    def _call_llm_async(self, messages: List["ChatCompletionMessageParam"], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run async LLM call in sync context using event loop."""
        if self._event_loop is None:
            raise RuntimeError("Event loop not initialized. Brain must be running.")
        
        return self._event_loop.run_until_complete(
            self._llm.chat_completion_async(
                messages=messages,
                tools=tools,
                tool_executor=self._tool_manager
            )
        )
    
    def _get_error_message(self, language: Optional[str]) -> str:
        """Get error message in user's language."""
        if language and language.startswith("zh"):
            return "对不对不起起，出现错误，请重试。"
        return "Sorry, an error occurred. Please try again."
