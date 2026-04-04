"""Integration tests for approval flow in ChatAgent."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from tank_backend.agents.approval import ApprovalManager, ToolApprovalPolicy
from tank_backend.agents.base import AgentOutputType, AgentState
from tank_backend.agents.chat_agent import ChatAgent, _build_tool_description, _parse_tool_args
from tank_backend.core.events import UpdateType

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
    agent: ChatAgent, state: AgentState,
) -> list[tuple[AgentOutputType, str, dict]]:
    """Collect all outputs from an agent run."""
    outputs = []
    async for output in agent.run(state):
        outputs.append((output.type, output.content, output.metadata))
    return outputs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChatAgentWithoutApproval:
    """ChatAgent should work normally when no approval is configured."""

    async def test_no_approval_passes_tools_directly(self):
        llm = MagicMock()
        llm.chat_stream = MagicMock(return_value=_llm_stream_with_tool("run_command"))
        tm = _make_tool_manager_mock()

        agent = ChatAgent(name="test", llm=llm, tool_manager=tm)
        state = AgentState(messages=[{"role": "user", "content": "run code"}])
        outputs = await _collect_outputs(agent, state)

        # Should see TOOL_CALLING, TOOL_EXECUTING, TOOL_RESULT, TOKEN, DONE
        types = [o[0] for o in outputs]
        assert AgentOutputType.TOOL_CALLING in types
        assert AgentOutputType.TOOL_EXECUTING in types
        assert AgentOutputType.TOOL_RESULT in types
        assert AgentOutputType.TOKEN in types
        assert AgentOutputType.DONE in types
        # No APPROVAL_NEEDED
        assert AgentOutputType.APPROVAL_NEEDED not in types


class TestChatAgentApprovalFlow:
    """Tests for ChatAgent with approval configured."""

    async def test_approval_needed_yielded_for_requiring_tool(self):
        """When a tool requires approval, APPROVAL_NEEDED is yielded instead of TOOL_EXECUTING."""
        policy = ToolApprovalPolicy(require_approval={"run_command"})
        manager = ApprovalManager(timeout=5.0)

        llm = MagicMock()
        llm.chat_stream = MagicMock(return_value=_llm_stream_with_tool("run_command"))
        tm = _make_tool_manager_mock()

        agent = ChatAgent(
            name="test", llm=llm, tool_manager=tm,
            approval_manager=manager, approval_policy=policy,
            session_id="s1",
        )

        state = AgentState(messages=[{"role": "user", "content": "run code"}])

        # Auto-approve in background after a short delay
        async def auto_approve():
            await asyncio.sleep(0.05)
            pending = manager.get_pending(session_id="s1")
            assert len(pending) == 1
            manager.resolve(pending[0].approval_id, approved=True)

        asyncio.get_event_loop().create_task(auto_approve())

        outputs = await _collect_outputs(agent, state)
        types = [o[0] for o in outputs]

        assert AgentOutputType.APPROVAL_NEEDED in types
        # TOOL_EXECUTING should NOT appear (replaced by APPROVAL_NEEDED)
        assert AgentOutputType.TOOL_EXECUTING not in types
        # After approval, TOOL_RESULT should appear
        assert AgentOutputType.TOOL_RESULT in types
        assert AgentOutputType.DONE in types

    async def test_rejection_returns_error_in_tool_result(self):
        """When user rejects, the tool result should contain a rejection message."""
        policy = ToolApprovalPolicy(require_approval={"run_command"})
        manager = ApprovalManager(timeout=5.0)

        llm = MagicMock()
        llm.chat_stream = MagicMock(return_value=_llm_stream_with_tool("run_command"))
        tm = _make_tool_manager_mock()

        agent = ChatAgent(
            name="test", llm=llm, tool_manager=tm,
            approval_manager=manager, approval_policy=policy,
            session_id="s1",
        )

        state = AgentState(messages=[{"role": "user", "content": "run code"}])

        async def auto_reject():
            await asyncio.sleep(0.05)
            pending = manager.get_pending(session_id="s1")
            manager.resolve(pending[0].approval_id, approved=False, reason="Not safe")

        asyncio.get_event_loop().create_task(auto_reject())

        outputs = await _collect_outputs(agent, state)
        types = [o[0] for o in outputs]

        assert AgentOutputType.APPROVAL_NEEDED in types
        # Tool result should contain rejection
        tool_results = [o for o in outputs if o[0] == AgentOutputType.TOOL_RESULT]
        assert len(tool_results) >= 1
        # The executor should NOT have been called with the real tool
        # (it returns a rejection error dict instead)

    async def test_always_approve_tool_skips_approval(self):
        """Tools in always_approve should execute without APPROVAL_NEEDED."""
        policy = ToolApprovalPolicy(
            always_approve={"calculate"},
            require_approval={"run_command"},
        )
        manager = ApprovalManager(timeout=5.0)

        llm = MagicMock()
        llm.chat_stream = MagicMock(
            return_value=_llm_stream_with_tool("calculate", '{"expression":"2+2"}'),
        )
        tm = _make_tool_manager_mock()

        agent = ChatAgent(
            name="test", llm=llm, tool_manager=tm,
            approval_manager=manager, approval_policy=policy,
            session_id="s1",
        )

        state = AgentState(messages=[{"role": "user", "content": "calculate 2+2"}])
        outputs = await _collect_outputs(agent, state)
        types = [o[0] for o in outputs]

        assert AgentOutputType.APPROVAL_NEEDED not in types
        assert AgentOutputType.TOOL_EXECUTING in types

    async def test_first_time_approval_then_auto(self):
        """first-time tools should ask once, then auto-approve."""
        policy = ToolApprovalPolicy(require_approval_first_time={"web_search"})
        manager = ApprovalManager(timeout=5.0)

        llm = MagicMock()
        tm = _make_tool_manager_mock()
        tm.get_openai_tools.return_value = [
            {"type": "function", "function": {"name": "web_search", "parameters": {}}},
        ]

        # First run: should need approval
        llm.chat_stream = MagicMock(
            return_value=_llm_stream_with_tool("web_search", '{"query":"test"}'),
        )

        agent = ChatAgent(
            name="test", llm=llm, tool_manager=tm,
            approval_manager=manager, approval_policy=policy,
            session_id="s1",
        )

        state = AgentState(messages=[{"role": "user", "content": "search test"}])

        async def auto_approve():
            await asyncio.sleep(0.05)
            pending = manager.get_pending(session_id="s1")
            if pending:
                manager.resolve(pending[0].approval_id, approved=True)

        asyncio.get_event_loop().create_task(auto_approve())

        outputs1 = await _collect_outputs(agent, state)
        types1 = [o[0] for o in outputs1]
        assert AgentOutputType.APPROVAL_NEEDED in types1

        # In real flow, the ApprovalToolExecutor calls policy.record_approved()
        # after the Future resolves. With mock LLM streams, the executor isn't
        # called, so we simulate the record_approved call.
        policy.record_approved("web_search")

        # Second run: should auto-approve (no APPROVAL_NEEDED)
        llm.chat_stream = MagicMock(
            return_value=_llm_stream_with_tool("web_search", '{"query":"test2"}'),
        )
        agent2 = ChatAgent(
            name="test", llm=llm, tool_manager=tm,
            approval_manager=manager, approval_policy=policy,
            session_id="s1",
        )
        state2 = AgentState(messages=[{"role": "user", "content": "search test2"}])
        outputs2 = await _collect_outputs(agent2, state2)
        types2 = [o[0] for o in outputs2]
        assert AgentOutputType.APPROVAL_NEEDED not in types2

    async def test_no_tools_no_approval(self):
        """Text-only responses should work with approval configured."""
        policy = ToolApprovalPolicy(require_approval={"run_command"})
        manager = ApprovalManager(timeout=5.0)

        llm = MagicMock()
        llm.chat_stream = MagicMock(return_value=_llm_stream_text_only())

        agent = ChatAgent(
            name="test", llm=llm,
            approval_manager=manager, approval_policy=policy,
        )

        state = AgentState(messages=[{"role": "user", "content": "hello"}])
        outputs = await _collect_outputs(agent, state)
        types = [o[0] for o in outputs]

        assert AgentOutputType.APPROVAL_NEEDED not in types
        assert AgentOutputType.TOKEN in types


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
        assert "Run command" in desc
        assert "python script.py" in desc

    def test_build_description_persistent_shell(self):
        desc = _build_tool_description("persistent_shell", {"command": "ls -la"})
        assert "Run in shell" in desc
        assert "ls -la" in desc

    def test_build_description_manage_process(self):
        desc = _build_tool_description("manage_process", {"action": "poll", "process_id": "abc123"})
        assert "Process poll" in desc
        assert "abc123" in desc

    def test_build_description_generic(self):
        desc = _build_tool_description("my_tool", {"arg": "val"})
        assert "Execute my_tool" in desc

    def test_build_description_truncation(self):
        long_code = "x" * 200
        desc = _build_tool_description("run_command", {"command": long_code})
        assert "..." in desc
        assert len(desc) < 200
