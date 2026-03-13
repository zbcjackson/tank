"""BrainProcessor — wraps Brain as a pipeline Processor."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import FlowReturn, Processor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ...core.brain import Brain
    from ...core.events import BrainInputEvent

logger = logging.getLogger(__name__)


class BrainProcessor(Processor):
    """Wraps Brain as a pipeline Processor.

    Input: BrainInputEvent
    Output: AudioOutputRequest (for TTS downstream)

    Delegates to the existing Brain.handle() method.
    Posts LLM latency metrics to Bus.
    Handles interrupt events by setting the runtime interrupt_event.
    """

    def __init__(self, brain: Brain, bus: Bus | None = None) -> None:
        super().__init__(name="brain")
        self._brain = brain
        self._bus = bus

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        event: BrainInputEvent = item

        started_at = time.time()

        # Delegate to existing Brain.handle() — it manages its own
        # conversation history, LLM calls, UI queue, and audio output queue.
        # Brain.handle() is synchronous (runs in its own thread with event loop).
        self._brain.handle(event)

        elapsed = time.time() - started_at

        if self._bus:
            self._bus.post(BusMessage(
                type="llm_latency",
                source=self.name,
                payload={
                    "latency_s": elapsed,
                    "user": event.user,
                    "text_length": len(event.text),
                },
            ))

        # Brain pushes results to its own queues (ui_queue, audio_output_queue)
        # so we don't yield output items here — the old Assistant still orchestrates.
        yield FlowReturn.OK, None

    def handle_event(self, event: PipelineEvent) -> bool:
        if event.type == "interrupt":
            # Set the runtime interrupt_event so Brain's streaming loop detects it
            runtime = self._brain._runtime
            if runtime.interrupt_event is not None:
                runtime.interrupt_event.set()
            return False  # propagate to other processors
        if event.type == "flush":
            return False  # propagate
        return False
