from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import time


@dataclass(frozen=True)
class AudioOutputRequest:
    """Single item for audio output queue: text to speak."""

    content: str
    language: str = "auto"
    voice: Optional[str] = None


class InputType(Enum):
    TEXT = auto()
    AUDIO = auto()
    SYSTEM = auto()


class UpdateType(Enum):
    """Types of updates for a streaming message."""
    THOUGHT = auto()     # Thinking process
    TOOL_CALL = auto()   # Tool call started/parameter update
    TOOL_RESULT = auto() # Tool execution result
    TEXT = auto()        # Final response text
    SIGNAL = auto()      # Status signals (processing_started/ended, etc.)


@dataclass(frozen=True)
class DisplayMessage:
    """One message for UI: who said it and what, with streaming support."""
    speaker: str  # e.g. "User", "Brain", "System", or voiceprint id
    text: str
    is_user: bool
    is_final: bool = True
    msg_id: Optional[str] = None
    update_type: UpdateType = UpdateType.TEXT
    metadata: dict = field(default_factory=dict)


@dataclass
class BrainInputEvent:
    type: InputType
    text: str
    user: str
    language: Optional[str]
    confidence: Optional[float]
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class BrainInterrupted(Exception):
    """Raised when Brain LLM processing is interrupted by user speech."""
