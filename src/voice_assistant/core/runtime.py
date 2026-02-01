"""Runtime context holding shared queues."""

from __future__ import annotations

from dataclasses import dataclass
import queue
from typing import TYPE_CHECKING

from .events import BrainInputEvent, DisplayMessage

if TYPE_CHECKING:
    from ..audio.output.types import AudioOutputRequest


@dataclass
class RuntimeContext:
    """
    Shared runtime objects owned by Assistant.

    Queues live here (not as globals) and are injected into components that need them.
    """

    brain_input_queue: "queue.Queue[BrainInputEvent]"
    audio_output_queue: "queue.Queue[AudioOutputRequest]"
    display_queue: "queue.Queue[DisplayMessage]"

    @classmethod
    def create(cls) -> "RuntimeContext":
        return cls(
            brain_input_queue=queue.Queue(),
            audio_output_queue=queue.Queue(),
            display_queue=queue.Queue(),
        )

