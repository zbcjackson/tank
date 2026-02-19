"""Runtime context holding shared queues and interrupt signal."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from .events import AudioOutputRequest, BrainInputEvent, UIMessage


@dataclass
class RuntimeContext:
    """
    Shared runtime objects owned by Assistant.

    Queues and interrupt_event live here and are injected into components that need them.
    """

    brain_input_queue: "queue.Queue[BrainInputEvent]"
    audio_output_queue: "queue.Queue[AudioOutputRequest]"
    ui_queue: "queue.Queue[UIMessage]"
    interrupt_event: threading.Event

    @classmethod
    def create(cls) -> "RuntimeContext":
        return cls(
            brain_input_queue=queue.Queue(),
            audio_output_queue=queue.Queue(),
            ui_queue=queue.Queue(),
            interrupt_event=threading.Event(),
        )

