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
                    "description": "Execute commands",
                    "tools": ["run_command"],
                },
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        # coder + auto-created verifier
        assert tm.register_tool.call_count == 2
        names = {call[0][0].get_info().name for call in tm.register_tool.call_args_list}
        assert "delegate_to_coder" in names
        assert "delegate_to_verifier" in names

    def test_multiple_workers_registered(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
                "researcher": {"description": "search", "tools": ["web_search"]},
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        # 2 workers + 1 auto-created verifier
        assert tm.register_tool.call_count == 3
        names = {call[0][0].get_info().name for call in tm.register_tool.call_args_list}
        assert names == {"delegate_to_coder", "delegate_to_researcher", "delegate_to_verifier"}

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

        # First registered tool is delegate_to_coder
        coder_tool = tm.register_tool.call_args_list[0][0][0]
        assert coder_tool.get_info().name == "delegate_to_coder"
        assert coder_tool._timeout == 42.0

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

    def test_no_parallel_fan_out_tool(self):
        """Parallel fan-out is handled by the LLM runtime, not a tool."""
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
                "researcher": {"description": "search", "tools": ["web_search"]},
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        names = {call[0][0].get_info().name for call in tm.register_tool.call_args_list}
        assert "parallel_fan_out" not in names


class TestAutoVerifier:
    """Verifier is auto-created when a coder worker exists."""

    def test_verifier_auto_created_with_coder(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        names = {call[0][0].get_info().name for call in tm.register_tool.call_args_list}
        assert "delegate_to_verifier" in names

    def test_verifier_not_created_without_coder(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "researcher": {"description": "search", "tools": ["web_search"]},
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        names = {call[0][0].get_info().name for call in tm.register_tool.call_args_list}
        assert "delegate_to_verifier" not in names

    def test_verifier_is_read_only(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        verifier_tools = [
            call[0][0] for call in tm.register_tool.call_args_list
            if call[0][0].get_info().name == "delegate_to_verifier"
        ]
        assert len(verifier_tools) == 1
        # Verifier's inner agent should only have read-only tools
        inner = verifier_tools[0]._worker_agent
        assert "file_write" not in (inner._tool_filter or [])
        assert "file_delete" not in (inner._tool_filter or [])

    def test_verifier_default_tools(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        verifier_tools = [
            call[0][0] for call in tm.register_tool.call_args_list
            if call[0][0].get_info().name == "delegate_to_verifier"
        ]
        inner = verifier_tools[0]._worker_agent
        assert inner._tool_filter == ["run_command", "file_read", "file_list"]

    def test_verifier_custom_config(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
            "verifier": {
                "tools": ["file_read"],
                "timeout": 60,
                "system_prompt": "Custom verifier prompt",
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        verifier_tools = [
            call[0][0] for call in tm.register_tool.call_args_list
            if call[0][0].get_info().name == "delegate_to_verifier"
        ]
        assert len(verifier_tools) == 1
        assert verifier_tools[0]._timeout == 60.0
        inner = verifier_tools[0]._worker_agent
        assert inner._tool_filter == ["file_read"]
        assert inner._system_prompt == "Custom verifier prompt"

    def test_explicit_verifier_worker_skips_auto_creation(self):
        """If user defines a verifier worker explicitly, don't auto-create."""
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
                "verifier": {"description": "custom verifier", "tools": ["file_read"]},
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        names = [call[0][0].get_info().name for call in tm.register_tool.call_args_list]
        # Should have delegate_to_coder and delegate_to_verifier, but NOT a duplicate
        assert names.count("delegate_to_verifier") == 1

    def test_orchestrator_prompt_includes_verifier(self):
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
        }
        agent = create_agent(
            "chat", llm=_make_llm(),
            tool_manager=_make_tool_manager(), config=config,
        )
        assert "delegate_to_verifier" in agent._system_prompt
        assert "VERDICT" in agent._system_prompt

    def test_orchestrator_prompt_mentions_verification_strategy(self):
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
            },
        }
        agent = create_agent(
            "chat", llm=_make_llm(),
            tool_manager=_make_tool_manager(), config=config,
        )
        assert "VERIFICATION" in agent._system_prompt


class TestParallelExecutionPrompt:
    """Parallel fan-out is handled by the LLM runtime (concurrent tool
    execution in llm.py), not a dedicated tool."""

    def test_orchestrator_prompt_mentions_parallel(self):
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
                "researcher": {"description": "search", "tools": ["web_search"]},
            },
        }
        agent = create_agent(
            "chat", llm=_make_llm(),
            tool_manager=_make_tool_manager(), config=config,
        )
        assert "PARALLEL" in agent._system_prompt or "concurrently" in agent._system_prompt

    def test_no_parallel_fan_out_tool_registered(self):
        tm = _make_tool_manager()
        config = {
            "workers": {
                "coder": {"description": "code", "tools": ["run_command"]},
                "researcher": {"description": "search", "tools": ["web_search"]},
            },
        }
        create_agent("chat", llm=_make_llm(), tool_manager=tm, config=config)

        names = {call[0][0].get_info().name for call in tm.register_tool.call_args_list}
        assert "parallel_fan_out" not in names
