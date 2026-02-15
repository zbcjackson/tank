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


@dataclass(frozen=True)
class DisplayMessage:
    """One message for UI: who said it and what."""

    speaker: str  # e.g. "User", "Brain", "System", or voiceprint id
    text: str
    is_user: bool
    is_final: bool = True
    msg_id: Optional[str] = None


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
