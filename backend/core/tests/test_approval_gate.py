"""Tests for ApprovalGateExecutor and ConfirmActionTool."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

from tank_backend.agents.approval import (
    ApprovalGateExecutor,
    InteractiveResolver,
    PendingToolCall,
    PendingToolCallStore,
    ToolApprovalPolicy,
)
from tank_backend.config.models import CommandSecurityConfig
from tank_backend.core.events import UpdateType
from tank_backend.pipeline.bus import Bus
from tank_backend.tools.base import ToolResult
from tank_backend.tools.confirm_action import ConfirmActionTool


class TestApprovalGateExecutor:
    """Tests for ApprovalGateExecutor — parks restricted tools instead of executing."""

    async def test_unrestricted_tool_delegates_to_manager(self):
        """Unrestricted tools should execute immediately via ToolManager."""
        policy = ToolApprovalPolicy()
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        tool_manager.execute_openai_tool_call = AsyncMock(return_value={"result": "42"})
        bus = Bus()

        gate = ApprovalGateExecutor(
            tool_manager=tool_manager,
            approval_policy=policy,
            resolver=InteractiveResolver(
                pending_store=store, session_id="s1", bus=bus,
                current_msg_id_fn=lambda: "msg1",
            ),
            pending_store=store,
            session_id="s1",
            bus=bus,
            current_msg_id_fn=lambda: "msg1",
        )

        # Mock tool_call for unrestricted tool
        tool_call = MagicMock()
        tool_call.function.name = "calculator"
        tool_call.function.arguments = '{"expression": "2+2"}'

        result = await gate.execute_openai_tool_call(tool_call)

        assert result == {"result": "42"}
        tool_manager.execute_openai_tool_call.assert_called_once_with(tool_call)
        assert store.get_oldest_pending() is None

    async def test_restricted_tool_parks_call(self):
        """Unknown commands should be parked in PendingToolCallStore."""
        from tank_backend.policy.command_security import CommandSecurityPolicy

        cmd_policy = CommandSecurityPolicy(CommandSecurityConfig())
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        bus = Bus()

        gate = ApprovalGateExecutor(
            tool_manager=tool_manager,
            approval_policy=policy,
            resolver=InteractiveResolver(
                pending_store=store, session_id="s1", bus=bus,
                current_msg_id_fn=lambda: "msg1",
            ),
            pending_store=store,
            session_id="s1",
            bus=bus,
            current_msg_id_fn=lambda: "msg1",
        )

        tool_call = MagicMock()
        tool_call.id = "call_123"
        tool_call.function.name = "run_command"
        tool_call.function.arguments = '{"command": "terraform apply"}'

        result = await gate.execute_openai_tool_call(tool_call)

        # Should return ToolResult with error
        assert isinstance(result, ToolResult)
        assert result.error is True
        assert "APPROVAL REQUIRED" in result.content

        # Should park the call
        pending = store.get_oldest_pending()
        assert pending is not None
        assert pending.tool_name == "run_command"
        assert pending.tool_args == {"command": "terraform apply"}
        assert pending.description == "terraform apply"

    async def test_dangerous_tool_hard_blocked(self):
        """Dangerous commands (DENY) should be hard-blocked without parking."""
        from tank_backend.policy.command_security import CommandSecurityPolicy

        cmd_policy = CommandSecurityPolicy(CommandSecurityConfig())
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        bus = Bus()

        gate = ApprovalGateExecutor(
            tool_manager=tool_manager,
            approval_policy=policy,
            resolver=InteractiveResolver(
                pending_store=store, session_id="s1", bus=bus,
                current_msg_id_fn=lambda: "msg1",
            ),
            pending_store=store,
            session_id="s1",
            bus=bus,
            current_msg_id_fn=lambda: "msg1",
        )

        tool_call = MagicMock()
        tool_call.id = "call_123"
        tool_call.function.name = "run_command"
        tool_call.function.arguments = '{"command": "rm -rf /"}'

        result = await gate.execute_openai_tool_call(tool_call)

        # Should return BLOCKED error, not APPROVAL REQUIRED
        assert isinstance(result, ToolResult)
        assert result.error is True
        assert "BLOCKED" in result.content
        tool_manager.execute_openai_tool_call.assert_not_called()

        # Should NOT park the call
        assert store.get_oldest_pending() is None

    async def test_restricted_tool_posts_approval_message(self):
        """Unknown commands should post APPROVAL ui_message to Bus."""
        from tank_backend.policy.command_security import CommandSecurityPolicy

        cmd_policy = CommandSecurityPolicy(CommandSecurityConfig())
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        bus = Bus()

        messages = []
        bus.subscribe("ui_message", lambda msg: messages.append(msg))

        gate = ApprovalGateExecutor(
            tool_manager=tool_manager,
            approval_policy=policy,
            resolver=InteractiveResolver(
                pending_store=store, session_id="s1", bus=bus,
                current_msg_id_fn=lambda: "msg1",
            ),
            pending_store=store,
            session_id="s1",
            bus=bus,
            current_msg_id_fn=lambda: "msg1",
        )

        tool_call = MagicMock()
        tool_call.id = "call_123"
        tool_call.function.name = "run_command"
        tool_call.function.arguments = '{"command": "terraform apply"}'

        await gate.execute_openai_tool_call(tool_call)

        # Bus uses queue + poll — dispatch pending messages
        bus.poll()

        assert len(messages) == 1
        msg = messages[0]
        assert msg.type == "ui_message"
        assert msg.payload.update_type == UpdateType.APPROVAL
        assert msg.payload.text == "terraform apply"


class TestConfirmActionTool:
    """Tests for ConfirmActionTool — executes or rejects parked tool calls."""

    async def test_no_pending_returns_error(self):
        """When no pending call exists, return error ToolResult."""
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        policy = ToolApprovalPolicy()

        tool = ConfirmActionTool(
            pending_store=store,
            tool_manager=tool_manager,
            approval_policy=policy,
        )

        result = await tool.execute(approved=True)

        assert isinstance(result, ToolResult)
        assert result.error is True
        assert "No pending action" in result.content

    async def test_approved_executes_tool(self):
        """When approved=True, execute the parked tool via ToolManager."""
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        tool_manager.execute_tool = AsyncMock(return_value={"output": "success"})
        policy = ToolApprovalPolicy()

        pending = PendingToolCall(
            approval_id="a1",
            tool_name="run_command",
            tool_args={"command": "ls"},
            tool_call_id="call_123",
            arguments_raw='{"command": "ls"}',
            description="ls",
            session_id="s1",
            created_at=time.time(),
        )
        store.park(pending)

        tool = ConfirmActionTool(
            pending_store=store,
            tool_manager=tool_manager,
            approval_policy=policy,
        )

        result = await tool.execute(approved=True)

        assert isinstance(result, ToolResult)
        assert result.error is False
        assert "Executed: ls" in result.display
        tool_manager.execute_tool.assert_called_once_with("run_command", command="ls")

    async def test_approved_records_approval(self):
        """When approved=True, the tool is executed successfully."""
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        tool_manager.execute_tool = AsyncMock(return_value={"output": "success"})
        policy = ToolApprovalPolicy()

        pending = PendingToolCall(
            approval_id="a1",
            tool_name="run_command",
            tool_args={"command": "ls"},
            tool_call_id="call_123",
            arguments_raw='{"command": "ls"}',
            description="ls",
            session_id="s1",
            created_at=time.time(),
        )
        store.park(pending)

        tool = ConfirmActionTool(
            pending_store=store,
            tool_manager=tool_manager,
            approval_policy=policy,
        )

        result = await tool.execute(approved=True)

        assert isinstance(result, ToolResult)
        assert result.error is False
        tool_manager.execute_tool.assert_called_once_with("run_command", command="ls")

    async def test_rejected_returns_rejection_result(self):
        """When approved=False, return rejection ToolResult without executing."""
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        tool_manager.execute_tool = AsyncMock()
        policy = ToolApprovalPolicy()

        pending = PendingToolCall(
            approval_id="a1",
            tool_name="run_command",
            tool_args={"command": "rm -rf /"},
            tool_call_id="call_123",
            arguments_raw='{"command": "rm -rf /"}',
            description="rm -rf /",
            session_id="s1",
            created_at=time.time(),
        )
        store.park(pending)

        tool = ConfirmActionTool(
            pending_store=store,
            tool_manager=tool_manager,
            approval_policy=policy,
        )

        result = await tool.execute(approved=False)

        assert isinstance(result, ToolResult)
        assert result.error is False
        assert "Rejected: rm -rf /" in result.display
        tool_manager.execute_tool.assert_not_called()

    async def test_consumes_pending_call(self):
        """After execution or rejection, pending call should be consumed."""
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        tool_manager.execute_tool = AsyncMock(return_value={"output": "success"})
        policy = ToolApprovalPolicy()

        pending = PendingToolCall(
            approval_id="a1",
            tool_name="run_command",
            tool_args={"command": "ls"},
            tool_call_id="call_123",
            arguments_raw='{"command": "ls"}',
            description="ls",
            session_id="s1",
            created_at=time.time(),
        )
        store.park(pending)

        tool = ConfirmActionTool(
            pending_store=store,
            tool_manager=tool_manager,
            approval_policy=policy,
        )

        await tool.execute(approved=True)

        # Should be consumed
        assert store.get_oldest_pending() is None

    async def test_tool_error_returns_error_result(self):
        """When tool execution fails, return error ToolResult."""
        store = PendingToolCallStore()
        tool_manager = MagicMock()
        tool_manager.execute_tool = AsyncMock(return_value={"error": "Command failed"})
        policy = ToolApprovalPolicy()

        pending = PendingToolCall(
            approval_id="a1",
            tool_name="run_command",
            tool_args={"command": "invalid"},
            tool_call_id="call_123",
            arguments_raw='{"command": "invalid"}',
            description="invalid",
            session_id="s1",
            created_at=time.time(),
        )
        store.park(pending)

        tool = ConfirmActionTool(
            pending_store=store,
            tool_manager=tool_manager,
            approval_policy=policy,
        )

        result = await tool.execute(approved=True)

        assert isinstance(result, ToolResult)
        assert result.error is True
        assert "Command failed" in result.display
