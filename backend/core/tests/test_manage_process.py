"""Tests for manage_process tool."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.sandbox.types import ProcessOutput
from tank_backend.tools.manage_process import ManageProcessTool


@pytest.fixture
def mock_sandbox():
    sandbox = MagicMock()
    sandbox.list_processes = MagicMock(return_value=[])
    sandbox.poll_process = AsyncMock()
    sandbox.process_log = AsyncMock(return_value="")
    sandbox.kill_process = AsyncMock()
    return sandbox


@pytest.fixture
def tool(mock_sandbox):
    return ManageProcessTool(mock_sandbox)


class TestManageProcessTool:
    def test_get_info(self, tool):
        info = tool.get_info()
        assert info.name == "manage_process"
        param_names = {p.name for p in info.parameters}
        assert "action" in param_names
        assert "process_id" in param_names

    async def test_list_empty(self, tool, mock_sandbox):
        result = await tool.execute(action="list")
        assert result["processes"] == []
        assert "No background" in result["message"]

    async def test_list_with_processes(self, tool, mock_sandbox):
        mock_sandbox.list_processes.return_value = [
            {
                "process_id": "abc123", "status": "running",
                "command": "./build.sh", "output_lines": 42,
            },
            {
                "process_id": "def456", "status": "exited",
                "command": "sleep 10", "output_lines": 0,
            },
        ]
        result = await tool.execute(action="list")
        assert len(result["processes"]) == 2
        assert "abc123" in result["message"]
        assert "def456" in result["message"]

    async def test_poll(self, tool, mock_sandbox):
        mock_sandbox.poll_process.return_value = ProcessOutput(
            output="new output\n", status="running"
        )
        result = await tool.execute(action="poll", process_id="abc123")
        assert result["output"] == "new output\n"
        mock_sandbox.poll_process.assert_awaited_once_with("abc123")

    async def test_poll_empty(self, tool, mock_sandbox):
        mock_sandbox.poll_process.return_value = ProcessOutput(
            output="", status="running"
        )
        result = await tool.execute(action="poll", process_id="abc123")
        assert result["message"] == "(no new output)"

    async def test_log(self, tool, mock_sandbox):
        mock_sandbox.process_log.return_value = "full history\n"
        result = await tool.execute(action="log", process_id="abc123")
        assert result["output"] == "full history\n"

    async def test_log_empty(self, tool, mock_sandbox):
        mock_sandbox.process_log.return_value = ""
        result = await tool.execute(action="log", process_id="abc123")
        assert result["message"] == "(no output history)"

    async def test_kill(self, tool, mock_sandbox):
        result = await tool.execute(action="kill", process_id="abc123")
        assert result["status"] == "killed"
        mock_sandbox.kill_process.assert_awaited_once_with("abc123")

    async def test_missing_process_id_for_non_list_action(self, tool):
        result = await tool.execute(action="poll")
        assert "error" in result
        assert "process_id required" in result["error"]

    async def test_unknown_action(self, tool):
        result = await tool.execute(action="restart", process_id="abc123")
        assert "error" in result
        assert "Unknown action" in result["error"]

    async def test_error_handling(self, tool, mock_sandbox):
        mock_sandbox.kill_process.side_effect = ValueError("not found")
        result = await tool.execute(action="kill", process_id="ghost")
        assert "error" in result
        assert "not found" in result["error"]
