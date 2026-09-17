"""Plugin-owned configuration; runtime authority is never configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True)
class N2SdkConfig:
    api_key: str
    base_url: str = "https://api.yutori.com/v1"
    model: str = "n2"
    tool_set: str = "computer_use_tools-20260830"
    reasoning_effort: str = "medium"
    max_steps: int = 100
    environment: str = "local"
    screenshot_delay: float = 0.5
    timeout_s: float = 600
    cleanup_timeout_s: float = 8

    def __post_init__(self) -> None:
        if (
            not isinstance(self.api_key, str)
            or not self.api_key.strip()
            or "${" in self.api_key
        ):
            raise ValueError("N2 SDK requires a resolved api_key (YUTORI_API_KEY)")
        if self.environment != "local":
            raise ValueError("N2 SDK supports environment=local only")
        if self.tool_set != "computer_use_tools-20260830":
            raise ValueError("N2 SDK requires computer_use_tools-20260830")
        if self.reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("invalid reasoning_effort")
        if type(self.max_steps) is not int or self.max_steps <= 0:
            raise ValueError("max_steps must be a positive integer (SDK model turns)")
        for name in ("screenshot_delay", "timeout_s", "cleanup_timeout_s"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be finite")
            if value < 0 or (name != "screenshot_delay" and value == 0):
                raise ValueError(f"{name} must be positive")
        if self.cleanup_timeout_s >= 10:
            raise ValueError(
                "cleanup_timeout_s must be below Tank's 10s cleanup deadline"
            )
        if not isinstance(self.base_url, str) or not self.base_url.startswith(
            "https://"
        ):
            raise ValueError("base_url must use https")
        if not isinstance(self.model, str) or not self.model:
            raise ValueError("model is required")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> N2SdkConfig:
        unknown = set(raw) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown N2 SDK configuration keys: {sorted(unknown)}")
        return cls(**{"api_key": "", **raw})
