"""Tests for agent creation with workers and tool routing."""

from unittest.mock import MagicMock

from tank_backend.agents.base import AgentOutputType, AgentState
from tank_backend.agents.factory import create_agent
from tank_backend.core.events import UpdateType


def _make_tool_manager(tool_names: list[str]) -> MagicMock:
    """Create a mock ToolManager with the given tool names."""
    tm = MagicMock()
    tm.get_openai_tools.return_value = [
        {"type": "function", "function": {"name": n, "description": f"{n} tool"}}
        for n in tool_names
    ]
    return tm


def _make_llm(events=None):
    """Create a mock LLM whose chat_stream returns a predefined sequence."""
    llm = MagicMock()

    async def chat_stream(messages, tools=None, **kwargs):
        for event in (events or [(UpdateType.TEXT, "ok", {"turn": 1})]):
            yield event

    llm.chat_stream = chat_stream
    return llm


class TestToolRouting:
    async def test_get_tools_includes_worker_tools_excludes_owned(self):
        """Worker tools visible, worker-owned tools hidden."""
        config = {
            "workers": {
                "coder": {
                    "description": "Run code",
                    "tools": ["run_command"],
                },
            },
        }
        agent = create_agent(
            "chat",
            llm=_make_llm(),
            tool_manager=_make_tool_manager(["run_command", "calculator", "weather"]),
            config=config,
        )

        tools, _executor = agent._get_tools()
        tool_names = {t["function"]["name"] for t in tools}

        assert "delegate_to_coder" in tool_names
        assert "calculator" in tool_names
        assert "weather" in tool_names
        assert "run_command" not in tool_names

    async def test_streams_tokens_with_workers(self):
        """Agent with workers still streams tokens normally."""
        events = [
            (UpdateType.TEXT, "Hello", {"turn": 1}),
            (UpdateType.TEXT, " there", {"turn": 1}),
        ]
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
        }
        agent = create_agent("chat", llm=_make_llm(events), config=config)

        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        outputs = [o async for o in agent.run(state)]

        tokens = [o.content for o in outputs if o.type == AgentOutputType.TOKEN]
        assert tokens == ["Hello", " there"]
        assert any(o.type == AgentOutputType.DONE for o in outputs)

    async def test_streams_tokens_without_workers(self):
        """Agent without workers streams tokens identically."""
        events = [
            (UpdateType.TEXT, "Hi", {"turn": 1}),
        ]
        agent = create_agent("chat", llm=_make_llm(events))

        state = AgentState(messages=[{"role": "user", "content": "hello"}])
        outputs = [o async for o in agent.run(state)]

        tokens = [o.content for o in outputs if o.type == AgentOutputType.TOKEN]
        assert tokens == ["Hi"]
