"""Tests for MCP client integration — client, proxy tool, tool group, and ToolManager."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.mcp.client import MCPClientManager, MCPServerConfig, load_mcp_configs
from tank_backend.mcp.proxy_tool import MCPProxyTool
from tank_backend.mcp.tool_group import MCPToolGroup

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_mcp_tool(name: str, description: str = "", input_schema: dict | None = None):
    """Create a mock MCP Tool object matching mcp.types.Tool shape."""
    return SimpleNamespace(
        name=name,
        description=description,
        inputSchema=input_schema or {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        },
    )


def _make_text_content(text: str):
    return SimpleNamespace(type="text", text=text)


def _make_image_content(data: bytes):
    return SimpleNamespace(type="image", data=data)


def _make_call_result(content: list, is_error: bool = False):
    return SimpleNamespace(content=content, isError=is_error)


def _make_list_result(tools: list):
    return SimpleNamespace(tools=tools)


def _make_app_config(**overrides):
    sections = {
        "network_access": {},
        "audit": {},
        "approval_policies": {},
        "sandbox": {},
        "file_access": {},
    }
    sections.update(overrides)
    cfg = MagicMock()
    cfg.get_section = MagicMock(
        side_effect=lambda key, default=None: sections.get(key, default or {}),
    )
    return cfg


# ------------------------------------------------------------------
# MCPServerConfig
# ------------------------------------------------------------------

class TestMCPServerConfig:
    def test_stdio_config(self):
        cfg = MCPServerConfig(
            name="fs", transport="stdio", command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        )
        assert cfg.name == "fs"
        assert cfg.transport == "stdio"
        assert cfg.command == "npx"
        assert cfg.approval == "require_approval"

    def test_http_config(self):
        cfg = MCPServerConfig(
            name="remote", transport="http",
            url="https://mcp.example.com/api",
            headers={"Authorization": "Bearer tok"},
        )
        assert cfg.transport == "http"
        assert cfg.url == "https://mcp.example.com/api"

    def test_default_approval(self):
        cfg = MCPServerConfig(name="x", transport="stdio", command="echo")
        assert cfg.approval == "require_approval"
        assert cfg.tool_overrides == {}


# ------------------------------------------------------------------
# MCPClientManager
# ------------------------------------------------------------------

class TestMCPClientManager:
    @pytest.mark.asyncio
    async def test_connect_stdio(self):
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=_make_list_result([]))

        with (
            patch("tank_backend.mcp.client.stdio_client") as mock_stdio,
            patch("tank_backend.mcp.client.ClientSession") as mock_cls,
        ):
            mock_read, mock_write = AsyncMock(), AsyncMock()
            mock_stdio.return_value.__aenter__ = AsyncMock(
                return_value=(mock_read, mock_write)
            )
            mock_stdio.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MCPClientManager()
            cfg = MCPServerConfig(name="test", transport="stdio", command="echo")
            await mgr.connect(cfg)

            assert "test" in mgr._sessions
            mock_session.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_http(self):
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with (
            patch("tank_backend.mcp.client.streamable_http_client") as mock_http,
            patch("tank_backend.mcp.client.ClientSession") as mock_cls,
        ):
            mock_read, mock_write = AsyncMock(), AsyncMock()
            mock_http.return_value.__aenter__ = AsyncMock(
                return_value=(mock_read, mock_write, None)
            )
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mgr = MCPClientManager()
            cfg = MCPServerConfig(
                name="remote", transport="http", url="https://example.com/mcp",
            )
            await mgr.connect(cfg)
            assert "remote" in mgr._sessions

    @pytest.mark.asyncio
    async def test_connect_stdio_missing_command(self):
        mgr = MCPClientManager()
        cfg = MCPServerConfig(name="bad", transport="stdio")
        with pytest.raises(ValueError, match="requires 'command'"):
            await mgr.connect(cfg)

    @pytest.mark.asyncio
    async def test_connect_http_missing_url(self):
        mgr = MCPClientManager()
        cfg = MCPServerConfig(name="bad", transport="http")
        with pytest.raises(ValueError, match="requires 'url'"):
            await mgr.connect(cfg)

    @pytest.mark.asyncio
    async def test_connect_all_partial_failure(self):
        mgr = MCPClientManager()
        good_cfg = MCPServerConfig(name="good", transport="stdio", command="echo")
        bad_cfg = MCPServerConfig(name="bad", transport="stdio")

        with (
            patch("tank_backend.mcp.client.stdio_client") as mock_stdio,
            patch("tank_backend.mcp.client.ClientSession") as mock_cls,
        ):
            mock_session = AsyncMock()
            mock_session.initialize = AsyncMock()
            mock_stdio.return_value.__aenter__ = AsyncMock(
                return_value=(AsyncMock(), AsyncMock())
            )
            mock_stdio.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            errors = await mgr.connect_all([good_cfg, bad_cfg])
            assert "bad" in errors
            assert "good" in mgr._sessions

    @pytest.mark.asyncio
    async def test_discover_tools(self):
        tool1 = _make_mcp_tool("read_file", "Read a file")
        tool2 = _make_mcp_tool("write_file", "Write a file")

        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(
            return_value=_make_list_result([tool1, tool2])
        )

        mgr = MCPClientManager()
        mgr._sessions["fs"] = mock_session

        discovered = await mgr.discover_tools()
        assert len(discovered) == 2
        assert discovered[0] == ("fs", tool1)
        assert discovered[1] == ("fs", tool2)

    @pytest.mark.asyncio
    async def test_discover_tools_handles_failure(self):
        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(side_effect=RuntimeError("disconnected"))

        mgr = MCPClientManager()
        mgr._sessions["broken"] = mock_session

        discovered = await mgr.discover_tools()
        assert discovered == []

    @pytest.mark.asyncio
    async def test_call_tool_text_result(self):
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_result(
                [_make_text_content("hello world")], is_error=False,
            )
        )

        mgr = MCPClientManager()
        mgr._sessions["fs"] = mock_session

        result = await mgr.call_tool("fs", "read_file", {"path": "/tmp/x"})
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_call_tool_error_result(self):
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_result(
                [_make_text_content("file not found")], is_error=True,
            )
        )

        mgr = MCPClientManager()
        mgr._sessions["fs"] = mock_session

        result = await mgr.call_tool("fs", "read_file", {"path": "/nope"})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "file not found" in parsed["error"]

    @pytest.mark.asyncio
    async def test_call_tool_image_content(self):
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_result(
                [_make_image_content(b"\x89PNG" * 10)], is_error=False,
            )
        )

        mgr = MCPClientManager()
        mgr._sessions["img"] = mock_session

        result = await mgr.call_tool("img", "screenshot", {})
        assert "image data" in result
        assert "40 bytes" in result

    @pytest.mark.asyncio
    async def test_call_tool_server_not_connected(self):
        mgr = MCPClientManager()
        result = await mgr.call_tool("missing", "tool", {})
        parsed = json.loads(result)
        assert "not connected" in parsed["error"]

    @pytest.mark.asyncio
    async def test_call_tool_exception(self):
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(side_effect=ConnectionError("broken pipe"))

        mgr = MCPClientManager()
        mgr._sessions["fs"] = mock_session

        result = await mgr.call_tool("fs", "read_file", {"path": "/x"})
        parsed = json.loads(result)
        assert "broken pipe" in parsed["error"]


# ------------------------------------------------------------------
# MCPProxyTool
# ------------------------------------------------------------------

class TestMCPProxyTool:
    def test_get_info_prefixed_name(self):
        mcp_tool = _make_mcp_tool("read_file", "Read a file")
        client = MagicMock()
        proxy = MCPProxyTool("filesystem", mcp_tool, client)

        info = proxy.get_info()
        assert info.name == "mcp_filesystem__read_file"
        assert "[filesystem]" in info.description
        assert "Read a file" in info.description
        assert info.parameters == []

    def test_get_raw_schema(self):
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        }
        mcp_tool = _make_mcp_tool("search", "Search", schema)
        proxy = MCPProxyTool("db", mcp_tool, MagicMock())

        assert proxy.get_raw_schema() == schema

    @pytest.mark.asyncio
    async def test_execute_delegates(self):
        mcp_tool = _make_mcp_tool("read_file")
        client = AsyncMock()
        client.call_tool = AsyncMock(return_value="file contents")

        proxy = MCPProxyTool("fs", mcp_tool, client)
        result = await proxy.execute(path="/tmp/test.txt")

        client.call_tool.assert_awaited_once_with("fs", "read_file", {"path": "/tmp/test.txt"})
        assert result == "file contents"

    def test_tool_name_format(self):
        mcp_tool = _make_mcp_tool("list_tables")
        proxy = MCPProxyTool("my_db", mcp_tool, MagicMock())
        assert proxy._tool_name == "mcp_my_db__list_tables"


# ------------------------------------------------------------------
# MCPToolGroup
# ------------------------------------------------------------------

class TestMCPToolGroup:
    def test_create_tools_empty_before_init(self):
        configs = [MCPServerConfig(name="fs", transport="stdio", command="echo")]
        group = MCPToolGroup(configs)
        assert group.create_tools() == []

    @pytest.mark.asyncio
    async def test_connect_servers_discovers_tools(self):
        tool1 = _make_mcp_tool("read_file", "Read")
        tool2 = _make_mcp_tool("write_file", "Write")

        configs = [MCPServerConfig(name="fs", transport="stdio", command="echo")]
        group = MCPToolGroup(configs)

        with (
            patch.object(group._client_manager, "connect_all", new_callable=AsyncMock) as mock_conn,
            patch.object(
                group._client_manager, "discover_tools", new_callable=AsyncMock,
            ) as mock_disc,
        ):
            mock_conn.return_value = {}
            mock_disc.return_value = [("fs", tool1), ("fs", tool2)]

            errors = await group.connect_servers()

        assert errors == {}
        tools = group.create_tools()
        assert len(tools) == 2
        names = {t.get_info().name for t in tools}
        assert names == {"mcp_fs__read_file", "mcp_fs__write_file"}

    @pytest.mark.asyncio
    async def test_connect_servers_returns_errors(self):
        configs = [
            MCPServerConfig(name="good", transport="stdio", command="echo"),
            MCPServerConfig(name="bad", transport="stdio", command="nope"),
        ]
        group = MCPToolGroup(configs)

        with (
            patch.object(group._client_manager, "connect_all", new_callable=AsyncMock) as mock_conn,
            patch.object(
                group._client_manager, "discover_tools", new_callable=AsyncMock,
            ) as mock_disc,
        ):
            mock_conn.return_value = {"bad": RuntimeError("fail")}
            mock_disc.return_value = [("good", _make_mcp_tool("tool1"))]

            errors = await group.connect_servers()

        assert "bad" in errors
        assert len(group.create_tools()) == 1

    def test_get_approval_overrides_server_default(self):
        configs = [MCPServerConfig(
            name="fs", transport="stdio", command="echo",
            approval="always_approve",
        )]
        group = MCPToolGroup(configs)

        mcp_tool = _make_mcp_tool("read_file")
        proxy = MCPProxyTool("fs", mcp_tool, MagicMock())
        group._tools.append(proxy)

        overrides = group.get_approval_overrides()
        assert overrides == {"mcp_fs__read_file": "always_approve"}

    def test_get_approval_overrides_per_tool(self):
        configs = [MCPServerConfig(
            name="fs", transport="stdio", command="echo",
            approval="always_approve",
            tool_overrides={"write_file": "require_approval"},
        )]
        group = MCPToolGroup(configs)

        read_tool = MCPProxyTool("fs", _make_mcp_tool("read_file"), MagicMock())
        write_tool = MCPProxyTool("fs", _make_mcp_tool("write_file"), MagicMock())
        group._tools.extend([read_tool, write_tool])

        overrides = group.get_approval_overrides()
        assert overrides["mcp_fs__read_file"] == "always_approve"
        assert overrides["mcp_fs__write_file"] == "require_approval"

    @pytest.mark.asyncio
    async def test_cleanup_delegates(self):
        configs = [MCPServerConfig(name="fs", transport="stdio", command="echo")]
        group = MCPToolGroup(configs)

        with patch.object(
            group._client_manager, "cleanup", new_callable=AsyncMock,
        ) as mock_cleanup:
            await group.cleanup()
            mock_cleanup.assert_awaited_once()


# ------------------------------------------------------------------
# load_mcp_configs
# ------------------------------------------------------------------

class TestLoadMCPConfigs:
    def test_loads_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "mcp_servers.yaml"
        yaml_file.write_text(
            "time:\n"
            "  transport: stdio\n"
            "  command: uvx\n"
            '  args: ["mcp-server-time"]\n'
            "  approval: always_approve\n"
        )
        configs = load_mcp_configs(yaml_file)
        assert len(configs) == 1
        assert configs[0].name == "time"
        assert configs[0].command == "uvx"
        assert configs[0].approval == "always_approve"

    def test_returns_empty_when_file_missing(self, tmp_path):
        configs = load_mcp_configs(tmp_path / "nonexistent.yaml")
        assert configs == []

    def test_returns_empty_for_empty_file(self, tmp_path):
        yaml_file = tmp_path / "mcp_servers.yaml"
        yaml_file.write_text("")
        configs = load_mcp_configs(yaml_file)
        assert configs == []

    def test_multiple_servers(self, tmp_path):
        yaml_file = tmp_path / "mcp_servers.yaml"
        yaml_file.write_text(
            "time:\n"
            "  command: uvx\n"
            '  args: ["mcp-server-time"]\n'
            "remote:\n"
            "  transport: http\n"
            "  url: https://example.com/mcp\n"
        )
        configs = load_mcp_configs(yaml_file)
        assert len(configs) == 2
        names = {c.name for c in configs}
        assert names == {"time", "remote"}


# ------------------------------------------------------------------
# ToolManager integration
# ------------------------------------------------------------------

_LOAD_MCP_PATCH = "tank_backend.mcp.client.load_mcp_configs"


class TestToolManagerMCPIntegration:
    def test_no_mcp_servers_no_group(self):
        with patch(_LOAD_MCP_PATCH, return_value=[]):
            cfg = _make_app_config()
            tm = _make_tool_manager(cfg)
        assert tm._mcp_group is None

    def test_mcp_group_created_from_config(self):
        configs = [MCPServerConfig(
            name="fs", transport="stdio", command="echo",
            approval="always_approve",
        )]
        with patch(_LOAD_MCP_PATCH, return_value=configs):
            cfg = _make_app_config()
            tm = _make_tool_manager(cfg)
        assert tm._mcp_group is not None

    @pytest.mark.asyncio
    async def test_connect_servers_registers_mcp_tools(self):
        configs = [MCPServerConfig(
            name="fs", transport="stdio", command="echo",
            approval="always_approve",
        )]
        with patch(_LOAD_MCP_PATCH, return_value=configs):
            cfg = _make_app_config()
            tm = _make_tool_manager(cfg)

        tool = _make_mcp_tool("read_file", "Read a file")
        with (
            patch.object(
                tm._mcp_group._client_manager, "connect_all", new_callable=AsyncMock,
            ) as mock_conn,
            patch.object(
                tm._mcp_group._client_manager, "discover_tools", new_callable=AsyncMock,
            ) as mock_disc,
        ):
            mock_conn.return_value = {}
            mock_disc.return_value = [("fs", tool)]

            await tm.connect_mcp_servers()

        assert "mcp_fs__read_file" in tm.tools

    @pytest.mark.asyncio
    async def test_connect_servers_merges_approval_overrides(self):
        configs = [MCPServerConfig(
            name="fs", transport="stdio", command="echo",
            approval="always_approve",
            tool_overrides={"write_file": "require_approval"},
        )]
        with patch(_LOAD_MCP_PATCH, return_value=configs):
            cfg = _make_app_config()
            tm = _make_tool_manager(cfg)

        read_tool = _make_mcp_tool("read_file")
        write_tool = _make_mcp_tool("write_file")
        with (
            patch.object(
                tm._mcp_group._client_manager, "connect_all", new_callable=AsyncMock,
            ) as mock_conn,
            patch.object(
                tm._mcp_group._client_manager, "discover_tools", new_callable=AsyncMock,
            ) as mock_disc,
        ):
            mock_conn.return_value = {}
            mock_disc.return_value = [("fs", read_tool), ("fs", write_tool)]

            await tm.connect_mcp_servers()

        policy = tm.approval_policy
        assert "mcp_fs__read_file" in policy._always_approve
        assert "mcp_fs__write_file" in policy._require_approval

    @pytest.mark.asyncio
    async def test_connect_servers_no_mcp_is_noop(self):
        with patch(_LOAD_MCP_PATCH, return_value=[]):
            cfg = _make_app_config()
            tm = _make_tool_manager(cfg)
        # Should not raise
        await tm.connect_mcp_servers()

    def test_get_openai_tools_uses_raw_schema(self):
        """MCP tools with raw schema bypass ToolParameter building."""
        with patch(_LOAD_MCP_PATCH, return_value=[]):
            cfg = _make_app_config()
            tm = _make_tool_manager(cfg)

        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL query"},
                "params": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Query parameters",
                },
            },
            "required": ["query"],
        }
        mcp_tool = _make_mcp_tool("query", "Run SQL", schema)
        proxy = MCPProxyTool("db", mcp_tool, MagicMock())
        tm.register_tool(proxy)

        openai_tools = tm.get_openai_tools()
        mcp_entry = next(
            t for t in openai_tools
            if t["function"]["name"] == "mcp_db__query"
        )
        assert mcp_entry["function"]["parameters"] == schema
        assert mcp_entry["function"]["description"] == "[db] Run SQL"

    def test_get_openai_tools_native_uses_tool_parameter(self):
        """Native tools still build schema from ToolParameter."""
        with patch(_LOAD_MCP_PATCH, return_value=[]):
            cfg = _make_app_config()
            tm = _make_tool_manager(cfg)

        openai_tools = tm.get_openai_tools()
        calc = next(
            t for t in openai_tools
            if t["function"]["name"] == "calculate"
        )
        params = calc["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


def _make_tool_manager(cfg):
    """Create ToolManager with mocked config."""
    from tank_backend.tools.manager import ToolManager
    return ToolManager(app_config=cfg)
