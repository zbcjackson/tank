"""Compare resolved M5 settings with the caller's pinned offline artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..agents.definition import AgentDefinition
from ..config import AppConfig
from ..llm.profile import LLMProfile, resolve_profile


def _definition(definition: AgentDefinition) -> dict[str, object]:
    value = asdict(definition)
    value["disallowed_tools"] = sorted(definition.disallowed_tools)
    value["skills"] = list(definition.skills)
    if definition.tool_filter is not None:
        value["tool_filter"] = list(definition.tool_filter)
    return value


def _profile(profile: LLMProfile) -> dict[str, object]:
    value = asdict(profile)
    del value["api_key"], value["name"]
    value["capabilities"] = sorted(profile.capabilities)
    return value


@dataclass(frozen=True)
class ComparisonContract:
    freeze_dir: Path
    variant: str

    def required_files(self, config_path: Path) -> tuple[Path, ...]:
        return (
            *(self.freeze_dir / name for name in
              ("manifest.json", "definitions.json", "profiles.json", "toolset.json")),
            *(config_path.parent / "agents").glob("*.md"),
        )

    def verify(self, config: AppConfig, definition: AgentDefinition) -> None:
        if self.variant not in {
            "A", "A-control", "B-host-only", "B-protocol-only", "B-combined", "C", "D",
        }:
            raise ValueError("Comparison contract requires one of the seven experiment variants")
        definitions = json.loads((self.freeze_dir / "definitions.json").read_text())
        profiles = json.loads((self.freeze_dir / "profiles.json").read_text())
        tools = json.loads((self.freeze_dir / "toolset.json").read_text())
        if _definition(definition) != definitions.get(self.variant):
            raise ValueError("Comparison contract agent definition mismatch")
        if config.agents.dirs != ["agents"] or config.agents.llm_profile != "planner":
            raise ValueError("Comparison contract agent resolution mismatch")
        if set(config.llm_profiles) != {"default", "planner", "locator"}:
            raise ValueError("Comparison contract profile names mismatch")
        for name in ("default", "planner", "locator"):
            source = "planner" if name == "default" else name
            expected = resolve_profile(source, {**profiles[source], "api_key": "unused"})
            if _profile(config.llm_profiles[name]) != _profile(expected):
                # Never print resolved values: headers/body may contain credentials.
                raise ValueError(f"Comparison contract profile mismatch: {name}")
        toolset = config.toolsets.profiles.get(definition.toolset)
        if not tools or toolset is None or list(toolset.tools) != tools:
            raise ValueError("Comparison contract toolset mismatch")
