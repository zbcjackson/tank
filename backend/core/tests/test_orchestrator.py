"""Tests for agent orchestration — definitions, runner, and agent tool."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tank_backend.agents.base import AgentOutputType
from tank_backend.core.events import UpdateType


def _make_tool_manager(tool_names: list[str] | None = None) -> MagicMock:
    """Create a mock ToolManager."""
    tm = MagicMock()
    names = tool_names or ["calculator", "run_command", "web_search"]
    tm.tools = {n: MagicMock() for n in names}

    def get_openai_tools(exclude=None):
        tools = [
            {"type": "function", "function": {"name": n, "description": f"{n} tool"}}
            for n in names
        ]
        if exclude:
            return [t for t in tools if t["function"]["name"] not in exclude]
        return tools

    tm.get_openai_tools = get_openai_tools
    return tm


def _make_llm(events=None):
    llm = MagicMock()

    async def chat_stream(messages, tools=None, tool_executor=None, **kwargs):
        for event in (events or [(UpdateType.TEXT, "ok", {"turn": 1})]):
            yield event

    llm.chat_stream = chat_stream
    return llm


# ---------------------------------------------------------------------------
# AgentDefinition tests
# ---------------------------------------------------------------------------

class TestAgentDefinition:
    def test_parse_valid_agent_file(self, tmp_path: Path) -> None:
        from tank_backend.agents.definition import parse_agent_file

        path = tmp_path / "coder.md"
        path.write_text(textwrap.dedent("""\
            ---
            name: coder
            description: "Execute code"
            disallowed-tools: [agent]
            skills: [commit]
            max-turns: 20
            background: false
            ---

            You are a coding agent.
        """))

        defn = parse_agent_file(path)
        assert defn.name == "coder"
        assert defn.description == "Execute code"
        assert defn.disallowed_tools == frozenset({"agent"})
        assert defn.skills == ("commit",)
        assert defn.max_turns == 20
        assert defn.background is False
        assert "coding agent" in defn.system_prompt

    def test_parse_missing_name(self, tmp_path: Path) -> None:
        from tank_backend.agents.definition import parse_agent_file

        path = tmp_path / "bad.md"
        path.write_text("---\ndescription: test\n---\nBody\n")

        with pytest.raises(ValueError, match="Missing required field 'name'"):
            parse_agent_file(path)

    def test_parse_missing_frontmatter(self, tmp_path: Path) -> None:
        from tank_backend.agents.definition import parse_agent_file

        path = tmp_path / "bad.md"
        path.write_text("Just text without frontmatter\n")

        with pytest.raises(ValueError, match="missing YAML frontmatter"):
            parse_agent_file(path)

    def test_parse_comma_separated_disallowed(self, tmp_path: Path) -> None:
        from tank_backend.agents.definition import parse_agent_file

        path = tmp_path / "test.md"
        path.write_text(
            "---\nname: test\ndescription: t\n"
            "disallowed-tools: agent, file_write\n---\nBody\n"
        )

        defn = parse_agent_file(path)
        assert defn.disallowed_tools == frozenset({"agent", "file_write"})

    def test_load_definitions_priority(self, tmp_path: Path) -> None:
        from tank_backend.agents.definition import load_agent_definitions

        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "coder.md").write_text(
            "---\nname: coder\ndescription: first\n---\nFirst\n"
        )
        (dir2 / "coder.md").write_text(
            "---\nname: coder\ndescription: second\n---\nSecond\n"
        )

        defs = load_agent_definitions([dir1, dir2])
        assert defs["coder"].description == "first"

    def test_load_definitions_nonexistent_dir(self, tmp_path: Path) -> None:
        from tank_backend.agents.definition import load_agent_definitions

        defs = load_agent_definitions([tmp_path / "nope"])
        assert defs == {}


# ---------------------------------------------------------------------------
# AgentRunner tests
# ---------------------------------------------------------------------------

class TestAgentRunner:
    def _make_runner(
        self, definitions: dict[str, Any] | None = None,
    ) -> Any:
        from tank_backend.agents.definition import AgentDefinition
        from tank_backend.agents.runner import AgentRunner

        defs = definitions or {
            "coder": AgentDefinition(
                name="coder",
                description="Execute code",
                system_prompt="You are a coder.",
            ),
            "researcher": AgentDefinition(
                name="researcher",
                description="Research",
                system_prompt="You are a researcher.",
                disallowed_tools=frozenset({"run_command", "file_write"}),
            ),
        }

        return AgentRunner(
            llm=_make_llm(),
            tool_manager=_make_tool_manager(),
            bus=MagicMock(),
            approval_manager=MagicMock(),
            approval_policy=MagicMock(),
            definitions=defs,
        )

    def test_get_definition(self) -> None:
        runner = self._make_runner()
        assert runner.get_definition("coder") is not None
        assert runner.get_definition("nonexistent") is None

    @pytest.mark.asyncio()
    async def test_run_agent_yields_outputs(self) -> None:

        runner = self._make_runner()
        defn = runner.get_definition("coder")
        assert defn is not None

        outputs = []
        async for output in runner.run_agent(
            agent_def=defn,
            messages=[{"role": "user", "content": "hello"}],
        ):
            outputs.append(output)

        assert len(outputs) > 0
        assert any(o.type == AgentOutputType.TOKEN for o in outputs)

    @pytest.mark.asyncio()
    async def test_depth_limit_enforced(self) -> None:
        from tank_backend.agents.definition import AgentDefinition
        from tank_backend.agents.runner import AgentRunner

        runner = AgentRunner(
            llm=_make_llm(),
            tool_manager=_make_tool_manager(),
            bus=MagicMock(),
            approval_manager=MagicMock(),
            approval_policy=MagicMock(),
            definitions={
                "coder": AgentDefinition(
                    name="coder",
                    description="code",
                    system_prompt="code",
                ),
            },
            max_depth=1,
        )

        defn = runner.get_definition("coder")
        assert defn is not None

        # First level: should work
        outputs = []
        async for output in runner.run_agent(
            agent_def=defn,
            messages=[{"role": "user", "content": "hello"}],
        ):
            outputs.append(output)
        assert any(o.type == AgentOutputType.TOKEN for o in outputs)

        # Get the agent_id from the first run
        agent_id = None
        for aid, _tracker in runner._active_agents.items():
            agent_id = aid
            break

        # Second level with parent: should be blocked (depth=1 >= max_depth=1)
        outputs2 = []
        async for output in runner.run_agent(
            agent_def=defn,
            messages=[{"role": "user", "content": "hello"}],
            parent_agent_id=agent_id,
        ):
            outputs2.append(output)

        assert any("max depth" in o.content for o in outputs2)


# ---------------------------------------------------------------------------
# AgentTool tests
# ---------------------------------------------------------------------------

class TestAgentTool:
    def test_get_info(self) -> None:
        from tank_backend.agents.agent_tool import AgentTool
        from tank_backend.agents.definition import AgentDefinition
        from tank_backend.agents.runner import AgentRunner

        runner = AgentRunner(
            llm=_make_llm(),
            tool_manager=_make_tool_manager(),
            bus=MagicMock(),
            approval_manager=MagicMock(),
            approval_policy=MagicMock(),
            definitions={
                "coder": AgentDefinition(
                    name="coder", description="code", system_prompt="code",
                ),
            },
        )

        tool = AgentTool(runner)
        info = tool.get_info()
        assert info.name == "agent"
        assert "coder" in info.description
        assert len(info.parameters) >= 2

    @pytest.mark.asyncio()
    async def test_execute_unknown_type(self) -> None:
        from tank_backend.agents.agent_tool import AgentTool
        from tank_backend.agents.runner import AgentRunner

        runner = AgentRunner(
            llm=_make_llm(),
            tool_manager=_make_tool_manager(),
            bus=MagicMock(),
            approval_manager=MagicMock(),
            approval_policy=MagicMock(),
            definitions={},
        )

        tool = AgentTool(runner)
        result = await tool.execute(prompt="hello", subagent_type="nonexistent")
        assert "error" in result

    @pytest.mark.asyncio()
    async def test_execute_coder(self) -> None:
        from tank_backend.agents.agent_tool import AgentTool
        from tank_backend.agents.definition import AgentDefinition
        from tank_backend.agents.runner import AgentRunner

        runner = AgentRunner(
            llm=_make_llm(),
            tool_manager=_make_tool_manager(),
            bus=MagicMock(),
            approval_manager=MagicMock(),
            approval_policy=MagicMock(),
            definitions={
                "coder": AgentDefinition(
                    name="coder", description="code", system_prompt="code",
                ),
            },
        )

        tool = AgentTool(runner)
        result = await tool.execute(prompt="write hello world", subagent_type="coder")
        assert "message" in result
        assert result["agent_type"] == "coder"
