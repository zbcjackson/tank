from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Structured tool result with separate LLM and UI content.

    This is the recommended return type for all tools.  It provides:
    - Strong typing (prevents accidental data loss)
    - Explicit separation of LLM content vs UI display
    - Clear error signaling

    Attributes:
        content: What the LLM sees — full data, never truncated.
        display: What the UI shows — human-friendly summary.
                 Falls back to truncated ``content`` when empty.
        error:   Whether this is an error result.

    Example::

        return ToolResult(
            content=json.dumps({"path": p, "data": text}),
            display=f"Read {p} ({len(text)} chars)",
        )
    """

    content: str
    display: str = ""
    error: bool = False


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
    async def execute(self, **kwargs) -> "ToolResult | str":
        """Execute the tool and return a result.

        Return conventions:
        - Return ``ToolResult`` for structured results (recommended).
          Provides explicit separation of LLM content vs UI display.
        - Return ``str`` for simple text results (e.g. skill instructions).
        - Never return ``dict`` — use ``ToolResult`` for type safety.

        Example::

            return ToolResult(
                content=json.dumps({"key": "value"}),
                display="Operation completed successfully",
            )
        """
        ...

    def get_raw_schema(self) -> dict | None:
        """Override to provide a raw JSON Schema for OpenAI function calling.

        When not None, ``ToolManager.get_openai_tools()`` uses this directly
        instead of building the schema from ``ToolParameter`` entries.
        """
        return None


class ToolGroup(ABC):
    """A cohesive set of tools that share construction dependencies."""

    @abstractmethod
    def create_tools(self) -> list[BaseTool]:
        """Return the tools this group provides."""
        ...

    async def cleanup(self) -> None:  # noqa: B027
        """Override for groups that own resources needing cleanup."""
