"""Tests for agent factory."""

from unittest.mock import MagicMock

from tank_backend.agents.chat_agent import ChatAgent
from tank_backend.agents.factory import create_agent


def _make_llm():
    return MagicMock()


class TestCreateAgent:
    def test_creates_chat_agent(self):
        agent = create_agent("chat", llm=_make_llm())
        assert isinstance(agent, ChatAgent)
        assert agent.name == "chat"

    def test_custom_name(self):
        agent = create_agent("my_agent", llm=_make_llm())
        assert agent.name == "my_agent"

    def test_system_prompt_from_config(self):
        agent = create_agent(
            "chat", llm=_make_llm(),
            config={"system_prompt": "You are a pirate."},
        )
        assert agent._system_prompt == "You are a pirate."

    def test_tool_manager_passed_through(self):
        tm = MagicMock()
        agent = create_agent("chat", llm=_make_llm(), tool_manager=tm)
        assert agent._tool_manager is tm

    def test_none_config_is_safe(self):
        agent = create_agent("chat", llm=_make_llm(), config=None)
        assert isinstance(agent, ChatAgent)

    def test_no_workers_means_no_extra_tools(self):
        agent = create_agent("chat", llm=_make_llm(), config={})
        assert len(agent._extra_tools) == 0
        assert len(agent._exclude_tools) == 0


class TestCreateAgentWithWorkers:
    def test_workers_create_extra_tools(self):
        config = {
            "workers": {
                "coder": {
                    "description": "Run code",
                    "tools": ["run_command"],
                },
            },
        }
        agent = create_agent("chat", llm=_make_llm(), config=config)
        assert isinstance(agent, ChatAgent)
        assert len(agent._extra_tools) == 1
        assert agent._extra_tools[0].get_info().name == "delegate_to_coder"

    def test_multiple_workers(self):
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
                "researcher": {"description": "search", "tools": ["web_search"]},
            },
        }
        agent = create_agent("chat", llm=_make_llm(), config=config)
        names = {t.get_info().name for t in agent._extra_tools}
        assert names == {"delegate_to_coder", "delegate_to_researcher"}

    def test_worker_owned_tools_excluded(self):
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
        }
        agent = create_agent("chat", llm=_make_llm(), config=config)
        assert "run_command" in agent._exclude_tools

    def test_worker_timeout(self):
        config = {
            "workers": {
                "coder": {
                    "description": "code",
                    "tools": ["run_command"],
                    "timeout": 42,
                },
            },
        }
        agent = create_agent("chat", llm=_make_llm(), config=config)
        assert agent._extra_tools[0]._timeout == 42.0

    def test_orchestrator_prompt_auto_generated(self):
        config = {
            "workers": {
                "coder": {"description": "Execute commands", "tools": ["run_command"]},
            },
        }
        agent = create_agent("chat", llm=_make_llm(), config=config)
        assert "delegate_to_coder" in agent._system_prompt
        assert "Execute commands" in agent._system_prompt

    def test_no_orchestrator_prompt_without_workers(self):
        agent = create_agent("chat", llm=_make_llm(), config={})
        assert agent._system_prompt is None

    def test_custom_system_prompt_overrides(self):
        config = {
            "system_prompt": "Custom prompt",
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
        }
        agent = create_agent("chat", llm=_make_llm(), config=config)
        assert agent._system_prompt == "Custom prompt"
