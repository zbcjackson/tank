from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import time

class InputType(Enum):
    TEXT = auto()
    AUDIO = auto()
    SYSTEM = auto()

@dataclass
class BrainInputEvent:
    type: InputType
    text: str
    user: str
    language: Optional[str]
    confidence: Optional[float]
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)
