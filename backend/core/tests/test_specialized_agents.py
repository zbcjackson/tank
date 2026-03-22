"""Tests for specialized agents (SearchAgent, TaskAgent, CodeAgent).

All specialized agents follow the same pattern: extend ChatAgent with a
custom system prompt and filtered tool set. These tests verify that the
specialization is correctly applied.
"""

from unittest.mock import MagicMock

from tank_backend.agents.base import AgentOutputType, AgentState
from tank_backend.agents.code_agent import CodeAgent
from tank_backend.agents.search_agent import SearchAgent
from tank_backend.agents.task_agent import TaskAgent
from tank_backend.core.events import UpdateType


def _make_llm(text="ok"):
    """Create a mock LLM that yields a single text token."""
    llm = MagicMock()

    async def chat_stream(messages, tools=None, tool_executor=None):
        yield (UpdateType.TEXT, text, {"turn": 1})

    llm.chat_stream = chat_stream
    return llm


class TestSearchAgent:
    def test_has_default_tool_filter(self):
        agent = SearchAgent(llm=_make_llm())
        assert "web_search" in agent._tool_filter
        assert "web_scraper" in agent._tool_filter

    def test_has_system_prompt(self):
        agent = SearchAgent(llm=_make_llm())
        assert agent._system_prompt is not None
        assert len(agent._system_prompt) > 0

    def test_custom_tool_filter(self):
        agent = SearchAgent(llm=_make_llm(), tool_filter=["web_search"])
        assert agent._tool_filter == ["web_search"]

    def test_custom_system_prompt(self):
        agent = SearchAgent(llm=_make_llm(), system_prompt="Custom prompt")
        assert agent._system_prompt == "Custom prompt"

    async def test_runs_and_yields_outputs(self):
        agent = SearchAgent(llm=_make_llm("search result"))
        state = AgentState(messages=[{"role": "user", "content": "find cats"}])

        outputs = [o async for o in agent.run(state)]
        tokens = [o for o in outputs if o.type == AgentOutputType.TOKEN]
        done = [o for o in outputs if o.type == AgentOutputType.DONE]

        assert len(tokens) == 1
        assert tokens[0].content == "search result"
        assert len(done) == 1

    async def test_prepends_system_prompt(self):
        captured = []

        async def chat_stream(messages, **kwargs):
            captured.extend(messages)
            yield (UpdateType.TEXT, "ok", {"turn": 1})

        llm = MagicMock()
        llm.chat_stream = chat_stream

        agent = SearchAgent(llm=llm)
        state = AgentState(messages=[{"role": "user", "content": "find"}])
        async for _ in agent.run(state):
            pass

        assert captured[0]["role"] == "system"
        assert "search" in captured[0]["content"].lower()


class TestTaskAgent:
    def test_has_default_tool_filter(self):
        agent = TaskAgent(llm=_make_llm())
        assert "calculate" in agent._tool_filter
        assert "get_time" in agent._tool_filter
        assert "get_weather" in agent._tool_filter

    def test_has_system_prompt(self):
        agent = TaskAgent(llm=_make_llm())
        assert agent._system_prompt is not None
        assert len(agent._system_prompt) > 0

    async def test_runs_and_yields_outputs(self):
        agent = TaskAgent(llm=_make_llm("42"))
        state = AgentState(messages=[{"role": "user", "content": "calc 6*7"}])

        outputs = [o async for o in agent.run(state)]
        tokens = [o for o in outputs if o.type == AgentOutputType.TOKEN]
        assert len(tokens) == 1
        assert tokens[0].content == "42"


class TestCodeAgent:
    def test_has_default_tool_filter(self):
        agent = CodeAgent(llm=_make_llm())
        assert "sandbox_exec" in agent._tool_filter
        assert "sandbox_bash" in agent._tool_filter

    def test_has_system_prompt(self):
        agent = CodeAgent(llm=_make_llm())
        assert agent._system_prompt is not None
        assert len(agent._system_prompt) > 0

    async def test_runs_and_yields_outputs(self):
        agent = CodeAgent(llm=_make_llm("print('hi')"))
        state = AgentState(messages=[{"role": "user", "content": "run hello world"}])

        outputs = [o async for o in agent.run(state)]
        tokens = [o for o in outputs if o.type == AgentOutputType.TOKEN]
        assert len(tokens) == 1
        assert tokens[0].content == "print('hi')"
