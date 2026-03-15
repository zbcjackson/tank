"""PlaybackProcessor — wraps audio playback as a pipeline Processor."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..bus import Bus, BusMessage
from ..event import PipelineEvent
from ..processor import FlowReturn, Processor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tank_contracts.tts import AudioChunk

logger = logging.getLogger(__name__)


class PlaybackProcessor(Processor):
    """Wraps audio playback as a pipeline Processor (terminal stage).

    Input: AudioChunk (PCM audio)
    Output: None (terminal — plays audio to speaker)

    Handles flush events (stop + fade out).
    Posts playback metrics to Bus.
    """

    def __init__(
        self,
        playback_callback: Any = None,
        bus: Bus | None = None,
    ) -> None:
        super().__init__(name="playback")
        self._playback_callback = playback_callback
        self._bus = bus
        self._chunk_count = 0
        self._flushed = False
        self._playing = False

        # Subscribe to tts_finished to know when all chunks have been sent
        if self._bus:
            self._bus.subscribe("tts_finished", self._on_tts_finished)

    def _on_tts_finished(self, _message: BusMessage) -> None:
        """TTS has finished generating — signal playback ended."""
        self._signal_playback_ended()

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        chunk: AudioChunk = item

        # New chunk arriving means upstream TTS started a new request —
        # clear the flushed flag so we don't drop the entire new response.
        if self._flushed:
            logger.info("PlaybackProcessor: clearing flushed flag for new TTS request")
            self._flushed = False
            self._chunk_count = 0

        self._chunk_count += 1

        # Signal playback started on first chunk
        if self._chunk_count == 1:
            self._playing = True
            has_cb = self._playback_callback is not None
            logger.info("PlaybackProcessor: received first chunk, callback=%s", has_cb)
            if self._bus:
                self._bus.post(BusMessage(
                    type="playback_started",
                    source=self.name,
                    payload=None,
                ))

        # Delegate to playback callback if provided
        if self._playback_callback is not None:
            self._playback_callback(chunk)
        else:
            logger.warning("PlaybackProcessor: no callback, dropping chunk %d", self._chunk_count)

        if self._bus and self._chunk_count % 50 == 0:
            self._bus.post(BusMessage(
                type="playback_progress",
                source=self.name,
                payload={"chunk_count": self._chunk_count},
            ))

        yield FlowReturn.OK, None

    def _signal_playback_ended(self) -> None:
        """Post playback_ended to bus if currently playing."""
        if self._playing:
            self._playing = False
            if self._bus:
                self._bus.post(BusMessage(
                    type="playback_ended",
                    source=self.name,
                    payload=None,
                ))

    def handle_event(self, event: PipelineEvent) -> bool:
        if event.type == "flush":
            self._signal_playback_ended()
            self._flushed = True
            self._chunk_count = 0
            logger.info("PlaybackProcessor: flushed")
            return True  # terminal — consume flush
        if event.type == "interrupt":
            self._signal_playback_ended()
            self._flushed = True
            self._chunk_count = 0
            logger.info("PlaybackProcessor: interrupted")
            return True  # terminal — consume interrupt
        return False

    async def start(self) -> None:
        self._flushed = False
        self._chunk_count = 0

    async def stop(self) -> None:
        self._flushed = True
