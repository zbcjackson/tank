"""Core processor abstraction for pipeline stages."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .event import PipelineEvent


class FlowReturn(Enum):
    """Result of pushing data through a processor."""

    OK = "ok"
    EOS = "eos"
    FLUSHING = "flushing"
    ERROR = "error"


@dataclass(frozen=True)
class AudioCaps:
    """Describes audio format capabilities of a processor."""

    sample_rate: int
    channels: int = 1
    dtype: str = "float32"


class Processor(ABC):
    """Base class for all pipeline processing stages."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.input_caps: AudioCaps | None = None
        self.output_caps: AudioCaps | None = None

    @abstractmethod
    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        """Process an input item and yield (status, output) pairs."""
        yield  # pragma: no cover

    def handle_event(self, event: PipelineEvent) -> bool:
        """Handle a pipeline event. Return True to stop propagation."""
        return False

    async def start(self) -> None:  # noqa: B027
        """Called when the pipeline starts. Override for setup."""

    async def stop(self) -> None:  # noqa: B027
        """Called when the pipeline stops. Override for teardown."""
