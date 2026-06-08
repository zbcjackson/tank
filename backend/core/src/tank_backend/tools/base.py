from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from ..core.content import ContentBlocks, normalize_content


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Structured tool result with separate LLM and UI content.

    This is the recommended return type for all tools.  It provides:
    - Strong typing (prevents accidental data loss)
    - Explicit separation of LLM content vs UI display
    - Clear error signaling

    Attributes:
        content: What the LLM sees. Either a plain ``str`` (backward-
                 compatible with pre-multimodal tools) or a list of
                 ``ContentBlock`` for multi-modal results (images, PDFs,
                 audio). String content is semantically equivalent to a
                 single ``TextBlock``.
        display: What the UI shows — human-friendly summary.
                 Falls back to a truncated text view of ``content`` when
                 empty.
        error:   Whether this is an error result.

    Example (text-only, unchanged from prior versions)::

        return ToolResult(
            content=json.dumps({"path": p, "data": text}),
            display=f"Read {p} ({len(text)} chars)",
        )

    Example (multi-modal — file_read returning an image)::

        return ToolResult(
            content=[
                TextBlock(text=f"Image at {p}"),
                ImageBlock(source=p, mime_type="image/png"),
            ],
            display=f"Read image {p}",
        )
    """

    content: str | ContentBlocks
    display: str = ""
    error: bool = False

    def to_blocks(self) -> ContentBlocks:
        """Return ``content`` as a block list.

        Wraps a plain ``str`` in a single ``TextBlock`` so callers can
        work with one shape regardless of how the tool chose to return.
        """
        return normalize_content(self.content)


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


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    """Declarative metadata for policy routing and guardrails.

    Tools override :meth:`BaseTool.get_metadata` to declare their
    category (used by :class:`ToolApprovalPolicy` to route to the
    correct security policy) and behavioral hints (idempotency,
    resource requirements).

    Attributes:
        category: Policy routing key. One of ``"command"``,
                  ``"file"``, ``"web"``, or ``"general"`` (default).
        idempotent: True for read-only / pure-query tools that
                    produce the same result for the same inputs.
                    Used by guardrails to detect no-progress loops.
        requires_network: Hint that the tool makes outbound requests.
        requires_filesystem: Hint that the tool accesses the filesystem.
    """

    category: str = "general"
    idempotent: bool = False
    requires_network: bool = False
    requires_filesystem: bool = False


# Phase 18: name of the reserved keyword argument that
# ``ToolManager.execute_tool`` injects when a tool's signature opts
# in to platform context. Tools that accept ``ctx: ToolContext``
# receive a populated :class:`ToolContext`; tools that don't are
# called as before. The name is centralised here so a future
# refactor (e.g. moving to a per-call context object) only changes
# one symbol.
TOOL_CONTEXT_KWARG = "ctx"


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Platform-owned context that tools may opt into.

    Phase 18 introduced this to give image-producing tools (``ChartTool``
    today, future image-generation tools) access to the
    :class:`MediaStore` and the current ``session_id``. The LLM never
    sees ``ToolContext`` — it's not in the tool's OpenAI schema. Tools
    declare ``ctx: ToolContext`` in their ``execute`` signature and
    :meth:`ToolManager.execute_tool` fills it in via the reserved
    :data:`TOOL_CONTEXT_KWARG`.

    Tools that don't need platform context just keep their current
    signatures (``**kwargs`` or named params); the manager only injects
    ``ctx`` when the target signature accepts it.

    Attributes:
        media_store: Session-scoped persistence for binary content
                     (PNG bytes from a chart, downloaded image, etc.).
                     ``None`` when the manager was constructed without
                     a MediaStore — tools should fall back to a clear
                     error result rather than crashing.
        session_id:  Current session/conversation id. Tools that
                     persist to MediaStore must pass this through
                     because :meth:`MediaStore.put` is session-scoped.
                     ``None`` when the manager hasn't been told about
                     a session yet (offline tool execution from CLI,
                     unit tests).
        bus:         Message bus for emitting events. Tools can use
                     this to post progress or domain-specific events.
                     ``None`` when running outside the pipeline.
    """

    media_store: Any = None
    session_id: str | None = None
    bus: Any = None


class BaseTool(ABC):
    @abstractmethod
    def get_info(self) -> ToolInfo:
        pass

    def get_metadata(self) -> ToolMetadata:
        """Return declarative metadata for policy routing and guardrails.

        Override in subclasses to declare category, idempotency, etc.
        Default: general category, mutable, no special requirements.
        """
        return ToolMetadata()

    def is_available(self) -> bool:
        """Return False to skip registration (missing env var, disabled config, etc.)."""
        return True

    @abstractmethod
    async def execute(self, **kwargs: Any) -> "ToolResult | str":
        """Execute the tool and return a result.

        Concrete tools narrow ``**kwargs`` to named parameters matching
        their OpenAI schema (e.g. ``url: str``, ``kind: str``). The
        base signature uses ``**kwargs: Any`` so pyright doesn't flag
        every override as ``reportIncompatibleMethodOverride`` — the
        dispatch site (``ToolManager.execute_tool``) always calls
        ``tool.execute(**arguments)`` where ``arguments`` is a dict
        from the LLM's JSON, so the runtime contract is "accept any
        keyword arguments the LLM sends."

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

    async def cleanup(self) -> None:
        """Override for groups that own resources needing cleanup."""
        return
