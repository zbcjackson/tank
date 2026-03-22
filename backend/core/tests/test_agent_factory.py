"""Tests for agent factory."""

from unittest.mock import MagicMock

import pytest

from tank_backend.agents.chat_agent import ChatAgent
from tank_backend.agents.code_agent import CodeAgent
from tank_backend.agents.factory import create_agent
from tank_backend.agents.search_agent import SearchAgent
from tank_backend.agents.task_agent import TaskAgent


def _make_llm():
    return MagicMock()


class TestCreateAgent:
    def test_creates_chat_agent(self):
        agent = create_agent("chat", "chat", llm=_make_llm())
        assert isinstance(agent, ChatAgent)
        assert agent.name == "chat"

    def test_creates_search_agent(self):
        agent = create_agent("search", "search", llm=_make_llm())
        assert isinstance(agent, SearchAgent)
        assert agent.name == "search"

    def test_creates_task_agent(self):
        agent = create_agent("task", "task", llm=_make_llm())
        assert isinstance(agent, TaskAgent)
        assert agent.name == "task"

    def test_creates_code_agent(self):
        agent = create_agent("code", "code", llm=_make_llm())
        assert isinstance(agent, CodeAgent)
        assert agent.name == "code"

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown agent type"):
            create_agent("x", "nonexistent", llm=_make_llm())

    def test_custom_name_overrides(self):
        agent = create_agent("my_search", "search", llm=_make_llm())
        assert agent.name == "my_search"

    def test_tool_filter_from_config(self):
        agent = create_agent(
            "search", "search", llm=_make_llm(),
            config={"tools": ["web_search"]},
        )
        assert agent._tool_filter == ["web_search"]

    def test_system_prompt_from_config(self):
        agent = create_agent(
            "chat", "chat", llm=_make_llm(),
            config={"system_prompt": "You are a pirate."},
        )
        assert agent._system_prompt == "You are a pirate."

    def test_tool_manager_passed_through(self):
        tm = MagicMock()
        agent = create_agent("chat", "chat", llm=_make_llm(), tool_manager=tm)
        assert agent._tool_manager is tm

    def test_none_config_is_safe(self):
        agent = create_agent("chat", "chat", llm=_make_llm(), config=None)
        assert isinstance(agent, ChatAgent)
