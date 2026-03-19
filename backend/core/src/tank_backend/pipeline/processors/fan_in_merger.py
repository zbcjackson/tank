"""FanInMerger — collects results from N branches, correlates, and emits merged output."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from ..bus import Bus, BusMessage
from ..processor import FlowReturn, Processor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeakerIDResult:
    """Result from the speaker identification branch."""

    utterance_id: str  # correlation key: f"{started_at_s:.3f}_{ended_at_s:.3f}"
    user_id: str


class FanInMerger(Processor):
    """Collects results from N branches, correlates by utterance_id, emits merged output.

    Receives items from a single queue (all branches push into it).
    Inspects type:
      - ``BrainInputEvent`` → ASR branch result
      - ``SpeakerIDResult`` → speaker identification branch result

    When all branches have reported for a given utterance_id, merges them
    (sets ``BrainInputEvent.user`` from ``SpeakerIDResult.user_id``) and emits.

    On timeout: emits with whatever is available (default user if speaker ID missing).
    """

    def __init__(
        self,
        branch_count: int = 2,
        timeout_s: float = 2.0,
        default_user: str = "User",
        bus: Bus | None = None,
    ) -> None:
        super().__init__(name="fan_in_merger")
        self._branch_count = branch_count
        self._timeout_s = timeout_s
        self._default_user = default_user
        self._bus = bus

        # Pending partial results keyed by utterance_id
        # Each value is a dict of branch results collected so far
        self._pending: dict[str, _PendingMerge] = {}

    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        from ...core.events import BrainInputEvent

        # Expire stale entries before processing
        self._expire_stale()

        if isinstance(item, BrainInputEvent):
            utterance_id = item.metadata.get("utterance_id")
            if utterance_id is None:
                # No utterance_id — pass through unmodified (e.g. keyboard input)
                yield FlowReturn.OK, item
                return

            pending = self._get_or_create(utterance_id)
            pending.brain_event = item

            merged = self._try_merge(utterance_id)
            if merged is not None:
                yield FlowReturn.OK, merged
            else:
                yield FlowReturn.OK, None

        elif isinstance(item, SpeakerIDResult):
            pending = self._get_or_create(item.utterance_id)
            pending.speaker_result = item

            merged = self._try_merge(item.utterance_id)
            if merged is not None:
                yield FlowReturn.OK, merged
            else:
                yield FlowReturn.OK, None

        else:
            # Unknown type — pass through
            yield FlowReturn.OK, item

    def _get_or_create(self, utterance_id: str) -> _PendingMerge:
        if utterance_id not in self._pending:
            self._pending[utterance_id] = _PendingMerge(created_at=time.monotonic())
        return self._pending[utterance_id]

    def _try_merge(self, utterance_id: str) -> Any | None:
        """Try to merge if all branches have reported. Returns merged event or None."""
        pending = self._pending.get(utterance_id)
        if pending is None:
            return None

        # Check if all branches reported
        parts_count = (1 if pending.brain_event is not None else 0) + (
            1 if pending.speaker_result is not None else 0
        )
        if parts_count < self._branch_count:
            return None

        # All branches reported — merge and emit
        return self._emit_merged(utterance_id, pending)

    def _emit_merged(self, utterance_id: str, pending: _PendingMerge) -> Any | None:
        """Merge pending results and clean up."""
        from ...core.events import BrainInputEvent, DisplayMessage

        brain_event = pending.brain_event
        if brain_event is None:
            # No ASR result — nothing to emit (speaker ID alone is useless)
            del self._pending[utterance_id]
            return None

        # Determine user from speaker ID result
        user = self._default_user
        if pending.speaker_result is not None:
            user = pending.speaker_result.user_id

        # Create new BrainInputEvent with merged user
        merged = BrainInputEvent(
            type=brain_event.type,
            text=brain_event.text,
            user=user,
            language=brain_event.language,
            confidence=brain_event.confidence,
            timestamp=brain_event.timestamp,
            metadata=brain_event.metadata,
        )

        if self._bus:
            self._bus.post(BusMessage(
                type="fan_in_merged",
                source=self.name,
                payload={
                    "utterance_id": utterance_id,
                    "user": user,
                    "had_speaker_id": pending.speaker_result is not None,
                },
            ))

            # Post corrected user transcript so the frontend shows the
            # identified speaker name instead of the generic "User".
            if pending.speaker_result is not None and user != brain_event.user:
                msg_id = brain_event.metadata.get("msg_id")
                self._bus.post(BusMessage(
                    type="ui_message",
                    source=self.name,
                    payload=DisplayMessage(
                        speaker=user,
                        text=brain_event.text,
                        is_user=True,
                        is_final=True,
                        msg_id=msg_id,
                    ),
                ))

        del self._pending[utterance_id]
        logger.debug("Merged utterance %s → user=%s", utterance_id, user)
        return merged

    def _expire_stale(self) -> None:
        """Expire pending entries that have timed out, emitting partial results."""
        now = time.monotonic()
        expired_ids = [
            uid
            for uid, p in self._pending.items()
            if (now - p.created_at) >= self._timeout_s
        ]
        for uid in expired_ids:
            pending = self._pending[uid]
            logger.warning(
                "FanInMerger: utterance %s timed out after %.1fs (asr=%s, speaker=%s)",
                uid,
                now - pending.created_at,
                pending.brain_event is not None,
                pending.speaker_result is not None,
            )
            # Emit whatever we have
            self._emit_merged(uid, pending)
            # _emit_merged already deletes from _pending

    def flush(self) -> None:
        """Clear all pending state (called on pipeline interrupt)."""
        count = len(self._pending)
        self._pending.clear()
        if count:
            logger.debug("FanInMerger flushed %d pending entries", count)

    def handle_event(self, event: Any) -> bool:
        if hasattr(event, "type") and event.type == "flush":
            self.flush()
        return False  # propagate


@dataclass
class _PendingMerge:
    """Internal state for a pending merge operation."""

    created_at: float
    brain_event: Any = None
    speaker_result: SpeakerIDResult | None = None
