"""SpeakerIDProcessor — wraps VoiceprintRecognizer as a pipeline Processor."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..bus import Bus, BusMessage
from ..processor import FlowReturn, Processor
from .fan_in_merger import SpeakerIDResult

if TYPE_CHECKING:
    from ...audio.input.voiceprint import VoiceprintRecognizer

logger = logging.getLogger(__name__)


class SpeakerIDProcessor(Processor):
    """Wraps VoiceprintRecognizer as a pipeline Processor.

    Input: VADResult (END_SPEECH with utterance PCM)
    Output: SpeakerIDResult(utterance_id, user_id)
    """

    def __init__(
        self,
        recognizer: VoiceprintRecognizer,
        bus: Bus | None = None,
    ) -> None:
        super().__init__(name="speaker_id")
        self._recognizer = recognizer
        self._bus = bus

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        from ...audio.input.vad import VADResult, VADStatus
        from ...audio.input.voiceprint import Utterance

        if not isinstance(item, VADResult):
            yield FlowReturn.OK, None
            return

        if item.status != VADStatus.END_SPEECH:
            yield FlowReturn.OK, None
            return

        if item.utterance_pcm is None or len(item.utterance_pcm) == 0:
            yield FlowReturn.OK, None
            return

        # Build correlation key matching ASRProcessor's utterance_id
        utterance_id = f"{item.started_at_s:.3f}_{item.ended_at_s:.3f}"

        utterance = Utterance(
            pcm=item.utterance_pcm,
            sample_rate=item.sample_rate or 16000,
            started_at_s=item.started_at_s or 0.0,
            ended_at_s=item.ended_at_s or 0.0,
        )

        user_id = self._recognizer.identify(utterance)

        if self._bus:
            self._bus.post(BusMessage(
                type="speaker_id_result",
                source=self.name,
                payload={
                    "utterance_id": utterance_id,
                    "user_id": user_id,
                },
            ))

        logger.debug("Speaker ID: utterance %s → %s", utterance_id, user_id)
        yield FlowReturn.OK, SpeakerIDResult(utterance_id=utterance_id, user_id=user_id)
