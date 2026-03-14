"""BrainProcessor — wraps Brain as a pipeline Processor."""

from __future__ import annotations

import logging
import queue
import threading
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

    Brain runs in its own QueueWorker thread. This processor:
    1. Pushes BrainInputEvent to Brain's input queue
    2. Runs a background thread that drains runtime.audio_output_queue
       and pushes AudioOutputRequest to the next pipeline queue
    3. UI messages are posted to Bus by Brain directly

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
        self._output_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._next_queue: Any = None  # Set by queue.chain()

    async def start(self) -> None:
        """Start the output draining thread."""
        self._stop_event.clear()
        self._output_thread = threading.Thread(
            target=self._drain_output_loop, name="BrainOutputDrain", daemon=True
        )
        self._output_thread.start()
        logger.debug("BrainProcessor output drain thread started")

    async def stop(self) -> None:
        """Stop the output draining thread."""
        self._stop_event.set()
        if self._output_thread is not None:
            self._output_thread.join(timeout=2.0)
            self._output_thread = None
        logger.debug("BrainProcessor output drain thread stopped")

    def _drain_output_loop(self) -> None:
        """Background thread: drain audio_output_queue and push to next queue."""
        rt = self._runtime or getattr(self._brain, "_runtime", None)
        if rt is None:
            logger.error("BrainProcessor: no runtime context, cannot drain outputs")
            return

        while not self._stop_event.is_set():
            try:
                # Drain audio_output_queue (non-blocking)
                try:
                    audio_req = rt.audio_output_queue.get(timeout=0.1)

                    # Push to next queue in pipeline (TTS)
                    if self._next_queue is not None:
                        result = self._next_queue.push(audio_req)
                except queue.Empty:
                    pass

                # Always drain ui_queue — regardless of whether audio_output had items
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
            except Exception:
                logger.error("BrainProcessor: error draining outputs", exc_info=True)

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        event: BrainInputEvent = item

        started_at = time.time()

        # Push event to Brain's input queue — Brain runs in its own QueueWorker
        # thread with its own event loop, so we can't call handle() directly
        # from the pipeline's async consumer (would nest event loops).
        rt = self._runtime or getattr(self._brain, "_runtime", None)
        if rt is not None:
            rt.brain_input_queue.put(event)
        else:
            logger.error("BrainProcessor: no runtime context, cannot push event")
            yield FlowReturn.ERROR, None
            return

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

        # Don't yield anything — outputs are drained by background thread
        yield FlowReturn.OK, None

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
