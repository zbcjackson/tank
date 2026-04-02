"""Tests for sandbox_exec tool."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.sandbox.types import ExecResult
from tank_backend.tools.sandbox_exec import SandboxExecTool


@pytest.fixture
def mock_sandbox():
    sandbox = MagicMock()
    sandbox.exec_command = AsyncMock()
    sandbox.ensure_container = AsyncMock()
    return sandbox


@pytest.fixture
def tool(mock_sandbox):
    return SandboxExecTool(mock_sandbox)


class TestSandboxExecTool:
    def test_get_info(self, tool):
        info = tool.get_info()
        assert info.name == "run_command"
        param_names = {p.name for p in info.parameters}
        assert "command" in param_names
        assert "timeout" in param_names
        assert "working_dir" in param_names
        assert "background" in param_names

    async def test_execute_success(self, tool, mock_sandbox):
        mock_sandbox.exec_command.return_value = ExecResult(
            stdout="hello world\n", stderr="", exit_code=0
        )
        result = await tool.execute(command="echo hello world")
        assert result["exit_code"] == 0
        assert "hello world" in result["message"]
        # working_dir default is now str(Path.home()), not "/workspace"
        call_args = mock_sandbox.exec_command.call_args
        assert call_args.kwargs["command"] == "echo hello world"
        assert call_args.kwargs["timeout"] == 120
        assert call_args.kwargs["background"] is False

    async def test_execute_with_stderr(self, tool, mock_sandbox):
        mock_sandbox.exec_command.return_value = ExecResult(
            stdout="", stderr="not found\n", exit_code=127
        )
        result = await tool.execute(command="bad_cmd")
        assert result["exit_code"] == 127
        assert "[stderr]" in result["message"]

    async def test_execute_timeout(self, tool, mock_sandbox):
        mock_sandbox.exec_command.return_value = ExecResult(
            stdout="partial", stderr="", exit_code=124, timed_out=True
        )
        result = await tool.execute(command="sleep 999", timeout=5)
        assert result["timed_out"] is True
        assert "timed out" in result["message"]

    async def test_execute_custom_working_dir(self, tool, mock_sandbox):
        mock_sandbox.exec_command.return_value = ExecResult(
            stdout="/tmp\n", stderr="", exit_code=0
        )
        await tool.execute(command="pwd", working_dir="/tmp")
        mock_sandbox.exec_command.assert_awaited_once_with(
            command="pwd", timeout=120, working_dir="/tmp",
            background=False,
        )

    async def test_execute_no_output(self, tool, mock_sandbox):
        mock_sandbox.exec_command.return_value = ExecResult(
            stdout="", stderr="", exit_code=0
        )
        result = await tool.execute(command="true")
        assert result["message"] == "(no output)"

    async def test_execute_error_handling(self, tool, mock_sandbox):
        mock_sandbox.exec_command.side_effect = RuntimeError("Docker not available")
        result = await tool.execute(command="echo hi")
        assert "error" in result
        assert "Docker not available" in result["error"]

    async def test_execute_background(self, tool, mock_sandbox):
        mock_sandbox.exec_command.return_value = ExecResult(
            stdout="abc123def456", stderr="", exit_code=0
        )
        result = await tool.execute(command="./build.sh", background=True)
        assert result["process_id"] == "abc123def456"
        assert "background" in result["message"].lower()
        # working_dir default is now str(Path.home()), not "/workspace"
        call_args = mock_sandbox.exec_command.call_args
        assert call_args.kwargs["command"] == "./build.sh"
        assert call_args.kwargs["timeout"] == 120
        assert call_args.kwargs["background"] is True
