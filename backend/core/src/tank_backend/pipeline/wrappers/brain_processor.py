"""BrainProcessor — wraps Brain as a pipeline Processor."""

from __future__ import annotations

import logging
import queue
import time
from typing import TYPE_CHECKING, Any

from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import FlowReturn, Processor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ...core.brain import Brain
    from ...core.events import BrainInputEvent
    from ...core.runtime import RuntimeContext

logger = logging.getLogger(__name__)


class BrainProcessor(Processor):
    """Wraps Brain as a pipeline Processor.

    Input: BrainInputEvent
    Output: AudioOutputRequest (for TTS downstream)

    Delegates to the existing Brain.handle() method.
    After handle() returns, drains the runtime queues:
    - audio_output_queue → yields each AudioOutputRequest downstream (→ TTS)
    - ui_queue → posts each UIMessage to Bus as "ui_message"

    Posts LLM latency metrics to Bus.
    Handles interrupt events by setting the runtime interrupt_event.
    """

    def __init__(
        self,
        brain: Brain,
        bus: Bus | None = None,
        runtime: RuntimeContext | None = None,
    ) -> None:
        super().__init__(name="brain")
        self._brain = brain
        self._bus = bus
        self._runtime = runtime

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

        # Drain runtime queues that Brain populated during handle()
        rt = self._runtime or getattr(self._brain, "_runtime", None)
        if rt is not None:
            # Drain audio_output_queue → yield downstream (→ TTS)
            while True:
                try:
                    audio_req = rt.audio_output_queue.get_nowait()
                    yield FlowReturn.OK, audio_req
                except queue.Empty:
                    break

            # Drain ui_queue → post to Bus as "ui_message"
            if self._bus:
                while True:
                    try:
                        ui_msg = rt.ui_queue.get_nowait()
                        self._bus.post(BusMessage(
                            type="ui_message",
                            source=self.name,
                            payload=ui_msg,
                        ))
                    except queue.Empty:
                        break

    def handle_event(self, event: PipelineEvent) -> bool:
        if event.type == "interrupt":
            # Set the runtime interrupt_event so Brain's streaming loop detects it
            rt = self._runtime or getattr(self._brain, "_runtime", None)
            if rt is not None and rt.interrupt_event is not None:
                rt.interrupt_event.set()
            return False  # propagate to other processors
        if event.type == "flush":
            return False  # propagate
        return False
