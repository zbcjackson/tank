import time
from dataclasses import dataclass, field
from enum import Enum, auto


@dataclass(frozen=True)
class AudioOutputRequest:
    """Single item for audio output queue: text to speak."""

    content: str
    language: str = "auto"
    voice: str | None = None


class InputType(Enum):
    TEXT = auto()
    AUDIO = auto()
    SYSTEM = auto()


class UpdateType(Enum):
    """Types of updates for a streaming message."""

    THOUGHT = auto()  # Thinking process
    TEXT = auto()  # Final response text
    TOOL = auto()  # Unified tool step: calling → executing → success/error


@dataclass(frozen=True)
class SignalMessage:
    """System signal for UI state changes (e.g., processing_started, processing_ended)."""

    signal_type: str
    msg_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DisplayMessage:
    """Content message for UI display (user input, assistant response, etc.)."""

    speaker: str  # e.g. "User", "Brain", or voiceprint id
    text: str
    is_user: bool
    is_final: bool = True
    msg_id: str | None = None
    update_type: UpdateType = UpdateType.TEXT
    metadata: dict = field(default_factory=dict)


# Type alias for messages in the UI queue
UIMessage = SignalMessage | DisplayMessage


@dataclass
class BrainInputEvent:
    type: InputType
    text: str
    user: str
    language: str | None
    confidence: float | None
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class BrainInterrupted(Exception):
    """Raised when Brain LLM processing is interrupted by user speech."""
