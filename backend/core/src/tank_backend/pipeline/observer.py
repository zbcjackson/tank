"""Pipeline observer protocol and base."""

from typing import Protocol, runtime_checkable

from ..bus import BusMessage


@runtime_checkable
class PipelineObserver(Protocol):
    """Protocol for pipeline observers that react to bus messages."""

    def on_message(self, message: BusMessage) -> None:
        """Handle a bus message."""
        ...
