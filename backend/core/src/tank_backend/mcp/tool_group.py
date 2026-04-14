"""MCPToolGroup — discovers and proxies tools from MCP servers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..tools.base import BaseTool, ToolGroup
from .client import MCPClientManager, MCPServerConfig
from .proxy_tool import MCPProxyTool

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MCPToolGroup(ToolGroup):
    """Tool group that connects to MCP servers and proxies their tools."""

    def __init__(self, configs: list[MCPServerConfig]) -> None:
        self._configs = configs
        self._client_manager = MCPClientManager()
        self._tools: list[BaseTool] = []

    def create_tools(self) -> list[BaseTool]:
        """Return discovered tools. Empty until async_init() is called."""
        return self._tools

    async def async_init(self) -> dict[str, Exception]:
        """Connect to all servers and discover tools.

        Must be called after construction. Returns {name: error} for failures.
        """
        errors = await self._client_manager.connect_all(self._configs)
        discovered = await self._client_manager.discover_tools()
        for server_name, mcp_tool in discovered:
            proxy = MCPProxyTool(server_name, mcp_tool, self._client_manager)
            self._tools.append(proxy)
        logger.info(f"MCP: {len(self._tools)} tools from {len(self._configs)} servers")
        return errors

    def get_approval_overrides(self) -> dict[str, str]:
        """Return {prefixed_tool_name: approval_tier} for all MCP tools."""
        overrides: dict[str, str] = {}
        cfg_by_name = {cfg.name: cfg for cfg in self._configs}
        for tool in self._tools:
            if not isinstance(tool, MCPProxyTool):
                continue
            cfg = cfg_by_name.get(tool._server_name)
            if cfg is None:
                continue
            mcp_name = tool._mcp_tool.name
            tier = cfg.tool_overrides.get(mcp_name, cfg.approval)
            overrides[tool._tool_name] = tier
        return overrides

    async def cleanup(self) -> None:
        await self._client_manager.cleanup()
