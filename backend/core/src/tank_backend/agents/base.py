"""Agent base classes and output protocol for the orchestration layer."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

logger = logging.getLogger(__name__)


class AgentOutputType(Enum):
    """Types of outputs an agent can yield."""

    TOKEN = auto()  # Streamed text token
    THOUGHT = auto()  # Reasoning/thinking content
    TOOL_CALLING = auto()  # Tool call being assembled
    TOOL_EXECUTING = auto()  # Tool execution in progress
    TOOL_RESULT = auto()  # Tool execution result (success or error)
    HANDOFF = auto()  # Route to another agent
    DONE = auto()  # Agent finished processing


@dataclass(frozen=True)
class AgentOutput:
    """Immutable output yielded by agents during streaming."""

    type: AgentOutputType
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    target_agent: str | None = None


@dataclass
class AgentState:
    """Mutable state passed between agents in the graph.

    Agents append to ``messages`` as they produce responses, so conversation
    history accumulates across handoffs within a single user turn.
    """

    messages: list[ChatCompletionMessageParam] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    agent_history: list[str] = field(default_factory=list)
    turn: int = 0


class Agent(ABC):
    """Abstract base class for all agents.

    Subclasses must implement ``run()``, which receives the current
    :class:`AgentState` and yields :class:`AgentOutput` items.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    async def run(self, state: AgentState) -> AsyncIterator[AgentOutput]:
        """Process state and yield outputs.

        Must yield at least one ``DONE`` output when finished, or a
        ``HANDOFF`` output to transfer control to another agent.
        """
        ...  # pragma: no cover
        # Make this an async generator by yielding nothing in the base
        yield  # type: ignore[misc]  # noqa: E701
