"""Tests for agent creation."""

from unittest.mock import MagicMock

from tank_backend.agents.llm_agent import LLMAgent


def _make_llm():
    return MagicMock()


def _make_tool_manager():
    tm = MagicMock()
    tm.get_openai_tools.return_value = []
    return tm


class TestCreateAgent:
    def test_creates_llm_agent(self):
        agent = LLMAgent(name="chat", llm=_make_llm())
        assert isinstance(agent, LLMAgent)
        assert agent.name == "chat"

    def test_custom_name(self):
        agent = LLMAgent(name="my_agent", llm=_make_llm())
        assert agent.name == "my_agent"

    def test_system_prompt(self):
        agent = LLMAgent(
            name="chat", llm=_make_llm(),
            system_prompt="You are a pirate.",
        )
        assert agent._system_prompt == "You are a pirate."

    def test_tool_manager_passed_through(self):
        tm = _make_tool_manager()
        agent = LLMAgent(name="chat", llm=_make_llm(), tool_manager=tm)
        assert agent._tool_manager is tm

    def test_no_exclude_tools_by_default(self):
        agent = LLMAgent(name="chat", llm=_make_llm())
        assert len(agent._exclude_tools) == 0

    def test_exclude_tools(self):
        agent = LLMAgent(
            name="chat", llm=_make_llm(),
            exclude_tools={"agent", "file_write"},
        )
        assert agent._exclude_tools == {"agent", "file_write"}
