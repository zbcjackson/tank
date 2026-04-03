from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: list[ToolParameter]


@runtime_checkable
class ApprovalCallback(Protocol):
    """Async callback for requesting path-specific approval inside a tool.

    File tools call this when ``FileAccessPolicy`` returns ``require_approval``
    for a specific path. This is separate from the agent-layer tool-name
    approval — it provides per-path granularity that works regardless of
    which execution path (agent, brain, plugin) invokes the tool.

    Returns True if approved, False if denied.
    """

    async def __call__(
        self, tool_name: str, path: str, operation: str, reason: str,
    ) -> bool: ...


class BaseTool(ABC):
    @abstractmethod
    def get_info(self) -> ToolInfo:
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass


class ToolGroup(ABC):
    """A cohesive set of tools that share construction dependencies."""

    @abstractmethod
    def create_tools(self) -> list[BaseTool]:
        """Return the tools this group provides."""
        ...
