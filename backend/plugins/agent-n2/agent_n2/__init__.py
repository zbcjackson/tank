"""Agent extension factory."""

from typing import Any

from tank_backend.computer.executor import DesktopExecutor
from tank_backend.llm.profile import LLMProfile

from .agent import N2Agent


def create_agent(config: dict[str, Any]) -> N2Agent:
    executor, profile = config.get("desktop_executor"), config.get("llm_profile")
    if not isinstance(executor, DesktopExecutor):
        raise ValueError("agent-n2 requires declared desktop_executor capability")
    if not isinstance(profile, LLMProfile):
        raise ValueError(
            "agent-n2 requires a valid llm_profile: configure llm.n2 and "
            "agent_engines.\"agent-n2:agent\".llm_profile: n2"
        )
    return N2Agent(executor, profile, max_steps=config.get("max_steps", 100),
                   reasoning_effort=config.get("reasoning_effort", "medium"),
                   tool_set=config.get("tool_set", "computer_use_tools-20260830"))
