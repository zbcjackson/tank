"""Agent extension factory."""

from typing import Any, cast

from tank_backend.computer.executor import DesktopExecutor
from tank_backend.llm.profile import LLMProfile

from .agent import N2Agent


def create_agent(config: dict[str, Any]) -> N2Agent:
    executor, profile = config.get("desktop_executor"), config.get("llm_profile")
    # Runtime Protocol checks use static lookup and reject the host's governed
    # proxy, whose methods are supplied by __getattr__. Check the same surface
    # through ordinary lookup without invoking any desktop operation.
    methods = (name for name, value in vars(DesktopExecutor).items()
               if not name.startswith("_") and callable(value))
    if not all(callable(getattr(executor, name, None)) for name in methods):
        raise ValueError("agent-n2 requires declared desktop_executor capability")
    if not isinstance(profile, LLMProfile):
        raise ValueError(
            "agent-n2 requires a valid llm_profile: configure llm.n2 and "
            "agent_engines.\"agent-n2:agent\".llm_profile: n2"
        )
    return N2Agent(cast(DesktopExecutor, executor), profile, task_context=config.get("task_context"),
                   max_steps=config.get("max_steps", 100),
                   reasoning_effort=config.get("reasoning_effort", "medium"),
                   tool_set=config.get("tool_set", "computer_use_tools-20260830"))
