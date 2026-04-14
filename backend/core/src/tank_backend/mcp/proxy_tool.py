"""MCPProxyTool — wraps a single MCP tool as a BaseTool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..tools.base import BaseTool, ToolInfo

if TYPE_CHECKING:
    from .client import MCPClientManager


class MCPProxyTool(BaseTool):
    """Proxy that delegates execution to an MCP server tool.

    Registered in ToolManager like any native tool. The LLM sees it
    as a regular function with a prefixed name: ``mcp_{server}__{tool}``.
    """

    def __init__(
        self,
        server_name: str,
        mcp_tool: Any,
        client_manager: MCPClientManager,
    ) -> None:
        self._server_name = server_name
        self._mcp_tool = mcp_tool
        self._client = client_manager
        self._tool_name = f"mcp_{server_name}__{mcp_tool.name}"

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name=self._tool_name,
            description=f"[{self._server_name}] {self._mcp_tool.description or ''}",
            parameters=[],
        )

    def get_raw_schema(self) -> dict | None:
        """Return the MCP tool's inputSchema directly for OpenAI function calling."""
        return self._mcp_tool.inputSchema

    async def execute(self, **kwargs: Any) -> Any:
        return await self._client.call_tool(
            self._server_name, self._mcp_tool.name, kwargs,
        )
