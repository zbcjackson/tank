"""MCP client manager — owns connections to external MCP servers.

The MCP SDK (anyio-based) spawns background tasks on the event loop where
``ClientSession`` is created.  In Tank the pipeline's ``ThreadedQueue``
workers each run their own ``asyncio.new_event_loop()``, so tool calls
arrive on a *different* loop than the one the session lives on.

To avoid a cross-loop deadlock we capture the "home" loop during
``connect()`` and, in ``call_tool()``, detect when we're on a foreign
loop and dispatch via ``run_coroutine_threadsafe`` back to the home loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MCPServerConfig(BaseModel):
    """Parsed from one entry in config.yaml mcp_servers."""

    name: str
    transport: Literal["stdio", "http"] = "stdio"
    # stdio fields
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    # http fields
    url: str | None = None
    headers: dict[str, str] = {}
    # approval
    approval: str = "require_approval"
    tool_overrides: dict[str, str] = {}


class MCPClientManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._server_configs: dict[str, MCPServerConfig] = {}
        # The event loop where sessions were created (set in connect).
        self._home_loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, config: MCPServerConfig) -> None:
        """Connect to one MCP server and store its session."""
        # Capture the loop so call_tool can dispatch back here.
        if self._home_loop is None:
            self._home_loop = asyncio.get_running_loop()
        if config.transport == "stdio":
            if not config.command:
                raise ValueError(f"MCP server '{config.name}': stdio transport requires 'command'")
            params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env or None,
            )
            transport = await self._exit_stack.enter_async_context(
                stdio_client(params)
            )
        elif config.transport == "http":
            if not config.url:
                raise ValueError(f"MCP server '{config.name}': http transport requires 'url'")
            transport = await self._exit_stack.enter_async_context(
                streamable_http_client(config.url)
            )
        else:
            raise ValueError(f"MCP server '{config.name}': unknown transport '{config.transport}'")

        read_stream, write_stream = transport[0], transport[1]
        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        self._sessions[config.name] = session
        self._server_configs[config.name] = config
        logger.info(f"MCP server '{config.name}' connected ({config.transport})")

    async def connect_all(
        self, configs: list[MCPServerConfig],
    ) -> dict[str, Exception]:
        """Connect to all configured servers. Returns {name: error} for failures."""
        errors: dict[str, Exception] = {}
        for cfg in configs:
            try:
                await self.connect(cfg)
            except Exception as e:
                logger.error(f"MCP server '{cfg.name}' failed to connect: {e}")
                errors[cfg.name] = e
        return errors

    async def discover_tools(self) -> list[tuple[str, Any]]:
        """List tools from all connected servers.

        Returns [(server_name, mcp.types.Tool), ...].
        """
        all_tools: list[tuple[str, Any]] = []
        for name, session in self._sessions.items():
            try:
                result = await session.list_tools()
                for tool in result.tools:
                    all_tools.append((name, tool))
                logger.info(
                    f"MCP server '{name}': discovered {len(result.tools)} tools"
                )
            except Exception as e:
                logger.error(f"Failed to list tools from MCP server '{name}': {e}")
        return all_tools

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any],
    ) -> str:
        """Call a tool on a specific server. Returns string result.

        If called from a foreign event loop (e.g. a ThreadedQueue worker),
        dispatches the actual RPC back to the home loop where the MCP
        session's background tasks are running.
        """
        session = self._sessions.get(server_name)
        if session is None:
            return json.dumps({"error": f"MCP server '{server_name}' not connected"})

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        on_home_loop = current_loop is self._home_loop

        if not on_home_loop and self._home_loop is not None:
            # We're on a ThreadedQueue worker loop — dispatch to home loop.
            future = asyncio.run_coroutine_threadsafe(
                self._do_call_tool(session, server_name, tool_name, arguments),
                self._home_loop,
            )
            try:
                return future.result(timeout=120)
            except Exception as e:
                logger.error(
                    f"MCP tool call failed (cross-loop): {server_name}/{tool_name}: {e}"
                )
                return json.dumps({"error": f"MCP tool call failed: {e}"})
        else:
            return await self._do_call_tool(session, server_name, tool_name, arguments)

    async def _do_call_tool(
        self,
        session: ClientSession,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Execute the actual MCP call_tool RPC on the home loop."""
        try:
            result = await session.call_tool(tool_name, arguments)
        except Exception as e:
            logger.error(
                f"MCP tool call failed: {server_name}/{tool_name}: {e}"
            )
            return json.dumps({"error": f"MCP tool call failed: {e}"})

        parts: list[str] = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            elif hasattr(content, "data"):
                parts.append(f"[{content.type} data: {len(content.data)} bytes]")
            else:
                parts.append(str(content))

        text = "\n".join(parts)
        if result.isError:
            return json.dumps({"error": text})
        return text

    async def cleanup(self) -> None:
        """Close all MCP server connections.

        The MCP SDK uses anyio cancel scopes internally.  If cleanup runs
        in a different asyncio Task than the one that opened the scopes
        (common during FastAPI shutdown), ``aclose`` raises
        ``RuntimeError("Attempted to exit cancel scope in a different
        task")``.  We catch that and fall back to letting the OS reap the
        subprocesses on exit.
        """
        try:
            await self._exit_stack.aclose()
        except RuntimeError as e:
            if "cancel scope" in str(e):
                logger.debug("MCP cleanup: cancel-scope mismatch (harmless): %s", e)
            else:
                raise
        finally:
            self._sessions.clear()
            self._server_configs.clear()
