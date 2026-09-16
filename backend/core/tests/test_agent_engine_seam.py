"""Tests for the B2 agent-engine seam.

Covers: ``engine:`` frontmatter field, manifest ``needs`` parsing,
registry agent-type validation, and the AgentRunner factory branch
(plugin agents instantiated via ExtensionRegistry instead of LLMAgent).
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType, AgentState
from tank_backend.agents.definition import AgentDefinition, parse_agent_file
from tank_backend.plugin.manifest import ExtensionManifest, read_manifest_from_yaml
from tank_backend.plugin.registry import ExtensionRegistry

# ---------------------------------------------------------------------------
# definition: engine field
# ---------------------------------------------------------------------------


def _write_agent_md(tmp_path: Path, frontmatter: str, body: str = "do things") -> Path:
    path = tmp_path / "agent.md"
    path.write_text(textwrap.dedent(f"---\n{frontmatter}\n---\n{body}"), "utf-8")
    return path


class TestEngineField:
    def test_parse_engine(self, tmp_path: Path):
        path = _write_agent_md(
            tmp_path, 'name: n2\ndescription: d\nengine: agent-n2:agent'
        )
        assert parse_agent_file(path).engine == "agent-n2:agent"

    def test_engine_absent_defaults_none(self, tmp_path: Path):
        path = _write_agent_md(tmp_path, "name: plain\ndescription: d")
        assert parse_agent_file(path).engine is None

    def test_definition_dataclass_default(self):
        d = AgentDefinition(name="x", description="", system_prompt="")
        assert d.engine is None


# ---------------------------------------------------------------------------
# manifest: needs capability declaration
# ---------------------------------------------------------------------------


class TestManifestNeeds:
    def test_parse_needs(self, tmp_path: Path):
        yaml_text = textwrap.dedent(
            """\
            name: agent-n2
            display_name: N2
            description: test
            extensions:
              - name: agent
                type: agent
                factory: agent_n2:create_agent
                needs: [desktop_executor]
            """
        )
        path = tmp_path / "plugin.yaml"
        path.write_text(yaml_text, "utf-8")
        manifest = read_manifest_from_yaml(path)
        assert manifest.extensions[0].needs == ("desktop_executor",)

    def test_needs_defaults_empty(self, tmp_path: Path):
        yaml_text = textwrap.dedent(
            """\
            name: p
            display_name: P
            description: d
            extensions:
              - name: tts
                type: tts
                factory: p:create
            """
        )
        path = tmp_path / "plugin.yaml"
        path.write_text(yaml_text, "utf-8")
        assert read_manifest_from_yaml(path).extensions[0].needs == ()


# ---------------------------------------------------------------------------
# registry: agent-type validation
# ---------------------------------------------------------------------------


class _NotAnAgent:
    pass


class _StubAgent(Agent):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(name="stub")
        self.config = config

    async def run(self, state: AgentState):
        yield AgentOutput(type=AgentOutputType.TOKEN, content="hi")
        yield AgentOutput(
            type=AgentOutputType.USAGE, metadata={"total_tokens": 7},
        )
        yield AgentOutput(type=AgentOutputType.DONE)


@pytest.fixture
def stub_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Importable module providing agent/non-agent factories."""
    mod = tmp_path / "_engine_seam_stub.py"
    mod.write_text(
        textwrap.dedent(
            f"""\
            from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType
            from tank_backend.agents.base import AgentState
            from typing import Any

            class {f"{_StubAgent.__name__}"}(Agent):
                def __init__(self, config):
                    super().__init__(name="stub")
                    self.config = config

                async def run(self, state):
                    yield AgentOutput(type=AgentOutputType.TOKEN, content="hi")
                    yield AgentOutput(
                        type=AgentOutputType.USAGE,
                        metadata={{"total_tokens": 7}},
                    )
                    yield AgentOutput(type=AgentOutputType.DONE)

            class {_NotAnAgent.__name__}:
                pass

            def create_agent(config):
                return {f"{_StubAgent.__name__}"}(config)

            def create_not_agent(config):
                return {_NotAnAgent.__name__}()
            """
        ),
        "utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "_engine_seam_stub"
    sys.modules.pop("_engine_seam_stub", None)


class TestRegistryValidation:
    def test_agent_type_requires_agent_abc(self, stub_module: str):
        registry = ExtensionRegistry()
        registry.register(
            "bad-plugin",
            ExtensionManifest(
                name="agent", type="agent",
                factory=f"{stub_module}:create_not_agent",
            ),
        )
        with pytest.raises(TypeError, match="Agent"):
            registry.instantiate("bad-plugin:agent", {})

    def test_valid_agent_passes(self, stub_module: str):
        registry = ExtensionRegistry()
        registry.register(
            "good-plugin",
            ExtensionManifest(
                name="agent", type="agent",
                factory=f"{stub_module}:create_agent",
            ),
        )
        instance = registry.instantiate("good-plugin:agent", {})
        assert isinstance(instance, Agent)

    def test_get_manifest(self, stub_module: str):
        registry = ExtensionRegistry()
        manifest = ExtensionManifest(
            name="agent", type="agent",
            factory=f"{stub_module}:create_agent",
            needs=("desktop_executor",),
        )
        registry.register("good-plugin", manifest)
        assert registry.get_manifest("good-plugin:agent") is manifest
        assert registry.get_manifest("missing:agent") is None


# ---------------------------------------------------------------------------
# AgentRunner factory branch
# ---------------------------------------------------------------------------


def _make_runner(registry: Any = None) -> Any:
    from tank_backend.agents.runner import AgentRunner

    return AgentRunner(
        llm=MagicMock(),
        tool_manager=MagicMock(),
        bus=MagicMock(),
        approval_policy=MagicMock(),
        pending_store=MagicMock(),
        definitions={},
        registry=registry,
    )


def _engine_definition() -> AgentDefinition:
    return AgentDefinition(
        name="computer_n2",
        description="d",
        system_prompt="sys",
        engine="agent-n2:agent",
    )


class TestRunnerEngineBranch:
    async def test_engine_agent_runs_and_streams(self):
        registry = MagicMock()
        registry.instantiate.return_value = _StubAgent({})
        registry.get_manifest.return_value = ExtensionManifest(
            name="agent", type="agent", factory="x:y",
        )
        runner = _make_runner(registry=registry)

        outputs = [
            o
            async for o in runner.run_agent(
                _engine_definition(), [{"role": "user", "content": "task"}]
            )
        ]

        types = [o.type for o in outputs]
        assert AgentOutputType.USAGE not in types  # consumed internally
        assert AgentOutputType.TOKEN in types
        assert AgentOutputType.DONE in types

    async def test_engine_without_registry_raises(self):
        runner = _make_runner(registry=None)
        with pytest.raises(RuntimeError, match="ExtensionRegistry"):
            async for _ in runner.run_agent(
                _engine_definition(), [{"role": "user", "content": "t"}]
            ):
                pass

    async def test_config_carries_executor_and_profile(self):
        registry = MagicMock()
        registry.instantiate.return_value = _StubAgent({})
        registry.get_manifest.return_value = ExtensionManifest(
            name="agent", type="agent", factory="x:y",
            needs=("desktop_executor",),
        )
        app_config = MagicMock()
        profile = MagicMock()
        app_config.get_llm_profile.return_value = profile
        runner = _make_runner(registry=registry)
        runner._app_config = app_config

        _ = [
            o
            async for o in runner.run_agent(
                _engine_definition(), [{"role": "user", "content": "t"}]
            )
        ]

        config = registry.instantiate.call_args[0][1]
        assert config["desktop_executor"] is not None
        assert config["llm_profile"] is profile
        assert config["system_prompt"]

    async def test_config_without_needs_gets_no_executor(self):
        registry = MagicMock()
        registry.instantiate.return_value = _StubAgent({})
        registry.get_manifest.return_value = ExtensionManifest(
            name="agent", type="agent", factory="x:y",
        )
        runner = _make_runner(registry=registry)

        _ = [
            o
            async for o in runner.run_agent(
                _engine_definition(), [{"role": "user", "content": "t"}]
            )
        ]

        config = registry.instantiate.call_args[0][1]
        assert config["desktop_executor"] is None

    async def test_missing_profile_degrades_to_none(self):
        registry = MagicMock()
        registry.instantiate.return_value = _StubAgent({})
        registry.get_manifest.return_value = ExtensionManifest(
            name="agent", type="agent", factory="x:y",
            needs=("desktop_executor",),
        )
        app_config = MagicMock()
        app_config.get_llm_profile.side_effect = KeyError("no profile")
        runner = _make_runner(registry=registry)
        runner._app_config = app_config

        _ = [
            o
            async for o in runner.run_agent(
                _engine_definition(), [{"role": "user", "content": "t"}]
            )
        ]

        config = registry.instantiate.call_args[0][1]
        assert config["llm_profile"] is None
