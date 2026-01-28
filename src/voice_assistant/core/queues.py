import queue
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any
import time

# Global Queues
# 1. BrainInputQueue: Perception -> Brain (BrainInputEvent) AND Keyboard -> Brain (BrainInputEvent)
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

brain_input_queue = queue.Queue()

# 2. AudioInputQueue: Mic -> Perception (Simulated raw audio data)
audio_input_queue = queue.Queue()

# 3. AudioOutputQueue: Brain -> Speaker (Text to be spoken, or audio chunks)
audio_output_queue = queue.Queue()

# 4. DisplayQueue: Brain/Others -> Main Thread (For strictly controlled printing)
display_queue = queue.Queue()
