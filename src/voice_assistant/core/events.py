from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import time


class InputType(Enum):
    TEXT = auto()
    AUDIO = auto()
    SYSTEM = auto()


@dataclass(frozen=True)
class DisplayMessage:
    """One message for UI: who said it and what."""

    speaker: str  # e.g. "User", "Brain", "System", or voiceprint id
    text: str


@dataclass
class BrainInputEvent:
    type: InputType
    text: str
    user: str
    language: Optional[str]
    confidence: Optional[float]
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)
