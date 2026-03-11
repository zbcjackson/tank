"""Tests for sandbox_process tool."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.tools.sandbox_process import SandboxProcessTool


@pytest.fixture
def mock_sandbox():
    sandbox = MagicMock()
    sandbox.list_sessions = MagicMock(return_value=[])
    sandbox.session_poll = AsyncMock(return_value="")
    sandbox.session_log = AsyncMock(return_value="")
    sandbox.session_write = AsyncMock()
    sandbox.session_kill = AsyncMock()
    sandbox.session_clear = MagicMock()
    sandbox.session_remove = AsyncMock()
    return sandbox


@pytest.fixture
def tool(mock_sandbox):
    return SandboxProcessTool(mock_sandbox)


class TestSandboxProcessTool:
    def test_get_info(self, tool):
        info = tool.get_info()
        assert info.name == "sandbox_process"
        param_names = {p.name for p in info.parameters}
        assert "action" in param_names
        assert "session" in param_names
        assert "input" in param_names

    async def test_list_empty(self, tool, mock_sandbox):
        result = await tool.execute(action="list")
        assert result["sessions"] == []
        assert "No active" in result["message"]

    async def test_list_with_sessions(self, tool, mock_sandbox):
        mock_sandbox.list_sessions.return_value = [
            {"name": "dev", "status": "running", "output_lines": 42},
            {"name": "bg", "status": "exited", "output_lines": 10},
        ]
        result = await tool.execute(action="list")
        assert len(result["sessions"]) == 2
        assert "dev" in result["message"]
        assert "bg" in result["message"]

    async def test_poll(self, tool, mock_sandbox):
        mock_sandbox.session_poll.return_value = "new output\n"
        result = await tool.execute(action="poll", session="dev")
        assert result["output"] == "new output\n"
        mock_sandbox.session_poll.assert_awaited_once_with("dev")

    async def test_poll_empty(self, tool, mock_sandbox):
        mock_sandbox.session_poll.return_value = ""
        result = await tool.execute(action="poll", session="dev")
        assert result["message"] == "(no new output)"

    async def test_log(self, tool, mock_sandbox):
        mock_sandbox.session_log.return_value = "full history\n"
        result = await tool.execute(action="log", session="dev")
        assert result["output"] == "full history\n"

    async def test_log_empty(self, tool, mock_sandbox):
        mock_sandbox.session_log.return_value = ""
        result = await tool.execute(action="log", session="dev")
        assert result["message"] == "(no output history)"

    async def test_write(self, tool, mock_sandbox):
        result = await tool.execute(action="write", session="dev", input="hello\n")
        assert result["status"] == "written"
        mock_sandbox.session_write.assert_awaited_once_with("dev", "hello\n")

    async def test_kill(self, tool, mock_sandbox):
        result = await tool.execute(action="kill", session="dev")
        assert result["status"] == "killed"
        mock_sandbox.session_kill.assert_awaited_once_with("dev")

    async def test_clear(self, tool, mock_sandbox):
        result = await tool.execute(action="clear", session="dev")
        assert result["status"] == "cleared"
        mock_sandbox.session_clear.assert_called_once_with("dev")

    async def test_remove(self, tool, mock_sandbox):
        result = await tool.execute(action="remove", session="dev")
        assert result["status"] == "removed"
        mock_sandbox.session_remove.assert_awaited_once_with("dev")

    async def test_missing_session_for_non_list_action(self, tool):
        result = await tool.execute(action="poll")
        assert "error" in result
        assert "Session name required" in result["error"]

    async def test_unknown_action(self, tool):
        result = await tool.execute(action="restart", session="dev")
        assert "error" in result
        assert "Unknown action" in result["error"]

    async def test_error_handling(self, tool, mock_sandbox):
        mock_sandbox.session_kill.side_effect = ValueError("not found")
        result = await tool.execute(action="kill", session="ghost")
        assert "error" in result
        assert "not found" in result["error"]
