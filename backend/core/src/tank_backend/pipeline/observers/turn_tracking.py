"""Turn tracking observer — counts conversation turns through the pipeline."""

import logging

from ..bus import Bus, BusMessage

logger = logging.getLogger(__name__)


class TurnTrackingObserver:
    """Tracks conversation turns by counting user_input and assistant_output events.

    Subscribes to "user_input" and "assistant_output" messages on the bus.
    """

    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._user_turns = 0
        self._assistant_turns = 0
        bus.subscribe("user_input", self.on_message)
        bus.subscribe("assistant_output", self.on_message)

    def on_message(self, message: BusMessage) -> None:
        if message.type == "user_input":
            self._user_turns += 1
            logger.debug("Turn tracking: user turn %d", self._user_turns)
        elif message.type == "assistant_output":
            self._assistant_turns += 1
            logger.debug("Turn tracking: assistant turn %d", self._assistant_turns)

    @property
    def user_turns(self) -> int:
        return self._user_turns

    @property
    def assistant_turns(self) -> int:
        return self._assistant_turns

    @property
    def total_turns(self) -> int:
        return self._user_turns + self._assistant_turns

    def reset(self) -> None:
        """Clear turn counts."""
        self._user_turns = 0
        self._assistant_turns = 0
