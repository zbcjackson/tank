import logging
import time
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from .events import BrainInputEvent, DisplayMessage
from .runtime import RuntimeContext
from .shutdown import StopSignal
from .worker import QueueWorker
from ..audio.output import SpeakerHandler
from ..config.settings import VoiceAssistantConfig

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam
    from ..llm.llm import LLM
    from ..tools.manager import ToolManager

logger = logging.getLogger("RefactoredAssistant")


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
        logger.info("Brain started. Thinking...")
        try:
            super().run()
        finally:
            logger.info("Brain stopped.")

    def handle(self, event: BrainInputEvent) -> None:
        """
        Handles inputs from both Keyboard and Perception.
        """
        logger.info(f"🧠 Processing {event.type} from {event.user}: {event.text}")

        # Simulate LLM Processing
        self._runtime.display_queue.put(
            DisplayMessage(speaker="Brain", text=f"Thinking about '{event.text}'...")
        )
        time.sleep(2.0)  # Simulate network latency

        response = f"I processed your input: {event.text}"

        # Send response to UI and Speaker
        self._runtime.display_queue.put(DisplayMessage(speaker="Brain", text=response))
        self._runtime.audio_output_queue.put({"type": "speech", "content": response})
