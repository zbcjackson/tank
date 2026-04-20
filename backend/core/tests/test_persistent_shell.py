"""Tests for persistent_shell tool."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.sandbox.types import BashResult
from tank_backend.tools.persistent_shell import PersistentShellTool


@pytest.fixture
def mock_sandbox():
    sandbox = MagicMock()
    sandbox.bash_command = AsyncMock()
    sandbox.ensure_container = AsyncMock()
    sandbox.session_write = AsyncMock()
    sandbox.session_read = AsyncMock()
    return sandbox


@pytest.fixture
def tool(mock_sandbox):
    return PersistentShellTool(mock_sandbox)


class TestPersistentShellTool:
    def test_get_info(self, tool):
        info = tool.get_info()
        assert info.name == "persistent_shell"
        param_names = {p.name for p in info.parameters}
        assert "command" in param_names
        assert "session" in param_names
        assert "action" in param_names
        assert "input" in param_names

    async def test_command_mode_default_session(self, tool, mock_sandbox):
        mock_sandbox.bash_command.return_value = BashResult(
            output="/workspace\n", session="default", exit_code=0
        )
        result = await tool.execute(command="pwd")
        data = json.loads(result.content)
        assert data["output"] == "/workspace\n"
        assert data["session"] == "default"
        mock_sandbox.bash_command.assert_awaited_once_with(
            command="pwd", session="default", timeout=120
        )

    async def test_command_mode_named_session(self, tool, mock_sandbox):
        mock_sandbox.bash_command.return_value = BashResult(
            output="ok\n", session="dev", exit_code=0
        )
        result = await tool.execute(command="echo ok", session="dev")
        data = json.loads(result.content)
        assert data["session"] == "dev"
        mock_sandbox.bash_command.assert_awaited_once_with(
            command="echo ok", session="dev", timeout=120
        )

    async def test_command_mode_empty_output(self, tool, mock_sandbox):
        mock_sandbox.bash_command.return_value = BashResult(
            output="", session="default", exit_code=0
        )
        result = await tool.execute(command="true")
        assert result.display == "(no output)"

    async def test_no_command_or_action_returns_error(self, tool):
        result = await tool.execute()
        assert result.error is True

    async def test_action_create(self, tool, mock_sandbox):
        mock_sandbox.bash_command.return_value = BashResult(
            output="", session="monitor", exit_code=0
        )
        result = await tool.execute(action="create", session="monitor")
        data = json.loads(result.content)
        assert data["status"] == "created"
        assert data["session"] == "monitor"

    async def test_action_write(self, tool, mock_sandbox):
        result = await tool.execute(action="write", session="dev", input="ls\n")
        data = json.loads(result.content)
        assert data["status"] == "written"
        mock_sandbox.session_write.assert_awaited_once_with("dev", "ls\n")

    async def test_action_read(self, tool, mock_sandbox):
        mock_sandbox.session_read.return_value = "file1.py\nfile2.py\n"
        result = await tool.execute(action="read", session="dev")
        data = json.loads(result.content)
        assert "file1.py" in data["output"]
        mock_sandbox.session_read.assert_awaited_once_with("dev")

    async def test_action_read_empty(self, tool, mock_sandbox):
        mock_sandbox.session_read.return_value = ""
        result = await tool.execute(action="read", session="dev")
        assert result.display == "(no new output)"

    async def test_unknown_action(self, tool):
        result = await tool.execute(action="invalid", session="dev")
        assert result.error is True
        data = json.loads(result.content)
        assert "Unknown action" in data["error"]

    async def test_error_handling(self, tool, mock_sandbox):
        mock_sandbox.bash_command.side_effect = RuntimeError("socket closed")
        result = await tool.execute(command="echo hi")
        assert result.error is True
        data = json.loads(result.content)
        assert "socket closed" in data["error"]
