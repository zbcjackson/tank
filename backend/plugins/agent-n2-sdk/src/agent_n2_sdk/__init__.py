"""Official N2 SDK plugin (loaded on demand)."""

from typing import Any

from .agent import N2SdkSubAgent
from .config import N2SdkConfig


def create_subagent(config: dict[str, Any]) -> N2SdkSubAgent:
    return N2SdkSubAgent(N2SdkConfig.from_dict(config))
