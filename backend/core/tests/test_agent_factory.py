"""Tests for agent factory."""

from unittest.mock import MagicMock

from tank_backend.agents.chat_agent import ChatAgent
from tank_backend.agents.factory import create_agent


def _make_llm():
    return MagicMock()


def _make_tool_manager():
    tm = MagicMock()
    tm.get_openai_tools.return_value = []
    return tm


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
        tm = _make_tool_manager()
        agent = create_agent("chat", llm=_make_llm(), tool_manager=tm)
        assert agent._tool_manager is tm

    def test_none_config_is_safe(self):
        agent = create_agent("chat", llm=_make_llm(), config=None)
        assert isinstance(agent, ChatAgent)

    def test_no_workers_means_no_exclude(self):
        agent = create_agent("chat", llm=_make_llm(), config={})
        assert len(agent._exclude_tools) == 0


class TestCreateAgentWithWorkers:
    def test_workers_registered_in_tool_manager(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {
                    "description": "Run code",
                    "tools": ["run_command"],
                },
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        # WorkerTool should have been registered via register_tool
        assert tm.register_tool.call_count == 1
        registered = tm.register_tool.call_args[0][0]
        assert registered.get_info().name == "delegate_to_coder"

    def test_multiple_workers_registered(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
                "researcher": {"description": "search", "tools": ["web_search"]},
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        assert tm.register_tool.call_count == 2
        names = {call[0][0].get_info().name for call in tm.register_tool.call_args_list}
        assert names == {"delegate_to_coder", "delegate_to_researcher"}

    def test_worker_owned_tools_excluded(self):
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
        }
        agent = create_agent(
            "chat", llm=_make_llm(),
            tool_manager=_make_tool_manager(), config=config,
        )
        assert "run_command" in agent._exclude_tools

    def test_worker_timeout(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {
                    "description": "code",
                    "tools": ["run_command"],
                    "timeout": 42,
                },
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        registered = tm.register_tool.call_args[0][0]
        assert registered._timeout == 42.0

    def test_orchestrator_prompt_auto_generated(self):
        config = {
            "workers": {
                "coder": {"description": "Execute commands", "tools": ["run_command"]},
            },
        }
        agent = create_agent(
            "chat", llm=_make_llm(),
            tool_manager=_make_tool_manager(), config=config,
        )
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
        agent = create_agent(
            "chat", llm=_make_llm(),
            tool_manager=_make_tool_manager(), config=config,
        )
        assert agent._system_prompt == "Custom prompt"
