"""Integration tests for approval flow in LLMAgent (state-machine approach)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from tank_backend.agents.approval import (
    PendingToolCallStore,
    ToolApprovalPolicy,
    _build_tool_description,
)
from tank_backend.agents.base import AgentOutputType, AgentState
from tank_backend.agents.llm_agent import LLMAgent, _parse_tool_args
from tank_backend.core.events import UpdateType
from tank_backend.pipeline.bus import Bus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_manager_mock() -> MagicMock:
    """Build a mock ToolManager with one tool: run_command."""
    tm = MagicMock()
    tm.get_openai_tools.return_value = [
        {"type": "function", "function": {"name": "run_command", "parameters": {}}},
        {"type": "function", "function": {"name": "calculate", "parameters": {}}},
    ]
    tm.execute_openai_tool_call = AsyncMock(return_value={"result": "42"})
    return tm


async def _llm_stream_with_tool(tool_name: str, tool_args: str = '{"code":"print(1)"}'):
    """Simulate LLM chat_stream that requests a single tool call."""
    # 1. Tool calling
    yield (UpdateType.TOOL, "", {
        "index": 0, "name": tool_name,
        "arguments": tool_args, "status": "calling", "turn": 1,
    })
    # 2. Tool executing
    yield (UpdateType.TOOL, "", {
        "index": 0, "name": tool_name,
        "arguments": tool_args, "status": "executing", "turn": 1,
    })
    # 3. Tool result (the executor will have been called by now in real LLM)
    yield (UpdateType.TOOL, "result: 42", {
        "index": 0, "name": tool_name, "status": "success", "turn": 1,
    })
    # 4. Text response
    yield (UpdateType.TEXT, "The answer is 42.", {})


async def _llm_stream_text_only():
    """Simulate LLM chat_stream with no tool calls."""
    yield (UpdateType.TEXT, "Hello ", {})
    yield (UpdateType.TEXT, "world!", {})


async def _collect_outputs(
    agent: LLMAgent, state: AgentState,
) -> list[tuple[AgentOutputType, str, dict]]:
    """Collect all outputs from an agent run."""
    outputs = []
    async for output in agent.run(state):
        outputs.append((output.type, output.content, output.metadata))
    return outputs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLLMAgentWithoutApproval:
    """LLMAgent should work normally when no approval is configured."""

    async def test_no_approval_passes_tools_directly(self):
        llm = MagicMock()
        llm.chat_stream = MagicMock(return_value=_llm_stream_with_tool("run_command"))
        tm = _make_tool_manager_mock()

        agent = LLMAgent(name="test", llm=llm, tool_manager=tm)
        state = AgentState(messages=[{"role": "user", "content": "run code"}])
        outputs = await _collect_outputs(agent, state)

        # Should see TOOL_CALLING, TOOL_EXECUTING, TOOL_RESULT, TOKEN, DONE
        types = [o[0] for o in outputs]
        assert AgentOutputType.TOOL_CALLING in types
        assert AgentOutputType.TOOL_EXECUTING in types
        assert AgentOutputType.TOOL_RESULT in types
        assert AgentOutputType.TOKEN in types
        assert AgentOutputType.DONE in types


class TestLLMAgentGateFlow:
    """Tests for LLMAgent with the state-machine approval gate."""

    async def test_restricted_tool_returns_error_via_gate(self):
        """When a command is dangerous, the gate returns an error dict
        instead of executing the tool."""
        from tank_backend.policy.command_security import CommandSecurityPolicy

        cmd_policy = CommandSecurityPolicy.from_dict({})
        policy = ToolApprovalPolicy(command_policy=cmd_policy)
        store = PendingToolCallStore()
        bus = Bus()

        # Mock the tool manager to track if it was called
        tm = _make_tool_manager_mock()
        tm.execute_openai_tool_call = AsyncMock(return_value={"result": "42"})

        # Create a gate executor directly to test its behavior
        from tank_backend.agents.approval import ApprovalGateExecutor

        gate = ApprovalGateExecutor(
            tool_manager=tm,
            approval_policy=policy,
            pending_store=store,
            session_id="s1",
            bus=bus,
            current_msg_id_fn=lambda: "msg1",
        )

        # Mock tool call — dangerous command
        tool_call = MagicMock()
        tool_call.id = "call_123"
        tool_call.function.name = "run_command"
        tool_call.function.arguments = '{"command": "rm -rf /"}'

        result = await gate.execute_openai_tool_call(tool_call)

        # Should return error dict, not execute
        assert "error" in result
        assert "APPROVAL REQUIRED" in result["error"]
        tm.execute_openai_tool_call.assert_not_called()

        # The pending store should have the parked call
        pending = store.get_oldest_pending()
        assert pending is not None
        assert pending.tool_name == "run_command"

    async def test_always_approve_tool_skips_gate(self):
        """Non-command tools should execute without being parked."""
        policy = ToolApprovalPolicy()
        store = PendingToolCallStore()
        bus = Bus()

        llm = MagicMock()
        llm.chat_stream = MagicMock(
            return_value=_llm_stream_with_tool("calculate", '{"expression":"2+2"}'),
        )
        tm = _make_tool_manager_mock()

        agent = LLMAgent(
            name="test", llm=llm, tool_manager=tm,
            approval_policy=policy,
            pending_store=store,
            bus=bus,
            session_id="s1",
        )

        state = AgentState(messages=[{"role": "user", "content": "calculate 2+2"}])
        outputs = await _collect_outputs(agent, state)
        types = [o[0] for o in outputs]

        assert AgentOutputType.TOOL_EXECUTING in types
        assert store.get_oldest_pending() is None

    async def test_no_tools_no_gate(self):
        """Text-only responses should work with approval configured."""
        policy = ToolApprovalPolicy()
        store = PendingToolCallStore()
        bus = Bus()

        llm = MagicMock()
        llm.chat_stream = MagicMock(return_value=_llm_stream_text_only())

        agent = LLMAgent(
            name="test", llm=llm,
            approval_policy=policy,
            pending_store=store,
            bus=bus,
        )

        state = AgentState(messages=[{"role": "user", "content": "hello"}])
        outputs = await _collect_outputs(agent, state)
        types = [o[0] for o in outputs]

        assert AgentOutputType.TOKEN in types
        assert store.get_oldest_pending() is None


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_parse_tool_args_valid_json(self):
        result = _parse_tool_args('{"code": "print(1)"}')
        assert result == {"code": "print(1)"}

    def test_parse_tool_args_invalid_json(self):
        result = _parse_tool_args("not json")
        assert result == {}

    def test_parse_tool_args_dict_passthrough(self):
        d = {"a": 1}
        result = _parse_tool_args(d)
        assert result is d

    def test_build_description_run_command(self):
        desc = _build_tool_description("run_command", {"command": "python script.py"})
        assert desc == "python script.py"

    def test_build_description_persistent_shell(self):
        desc = _build_tool_description("persistent_shell", {"command": "ls -la"})
        assert desc == "ls -la"

    def test_build_description_manage_process(self):
        desc = _build_tool_description("manage_process", {"action": "poll", "process_id": "abc123"})
        assert "Process poll" in desc
        assert "abc123" in desc

    def test_build_description_generic(self):
        desc = _build_tool_description("my_tool", {"arg": "val"})
        assert "my_tool" in desc
        assert "val" in desc

    def test_build_description_no_truncation(self):
        long_code = "x" * 200
        desc = _build_tool_description("run_command", {"command": long_code})
        assert desc == long_code
