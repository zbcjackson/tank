"""Pipeline events for inter-stage communication."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventDirection(Enum):
    """Direction of event propagation."""

    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"


@dataclass(frozen=True)
class PipelineEvent:
    """Event that propagates through the pipeline."""

    type: str
    direction: EventDirection = EventDirection.DOWNSTREAM
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
