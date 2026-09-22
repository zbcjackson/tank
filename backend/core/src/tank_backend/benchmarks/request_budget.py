"""Per-trial HTTP admission limits; no token/cost estimates or automatic retries."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Literal


class RequestLimitExceeded(RuntimeError):
    """A request was refused locally; this says nothing about desktop cleanup."""


@dataclass(frozen=True)
class RequestLimits:
    planner: int = 16
    locator: int = 15
    total: int = 31

    def __post_init__(self) -> None:
        if any(type(n) is not int or n < 0 for n in (self.planner, self.locator, self.total)):
            raise ValueError("Request limits must be non-negative integers")


@dataclass
class RequestBudget:
    limits: RequestLimits
    planner: int = 0
    locator: int = 0
    blocked: bool = False
    active: bool = True

    def reserve(self, role: Literal["planner", "locator"]) -> None:
        if not self.active:
            raise RequestLimitExceeded("request outside active trial")
        if self.blocked:
            raise RequestLimitExceeded("request budget already stopped")
        used = self.locator if role == "locator" else self.planner
        cap = self.limits.locator if role == "locator" else self.limits.planner
        if used >= cap or self.planner + self.locator >= self.limits.total:
            self.blocked = True
            raise RequestLimitExceeded(f"request limit reached: {role}={used}/{cap}, "
                                       f"total={self.planner + self.locator}/{self.limits.total}")
        if role == "locator":
            self.locator += 1
        else:
            self.planner += 1

    def snapshot(self) -> dict[str, object]:
        return {"limits": asdict(self.limits), "planner": self.planner,
                "locator": self.locator, "total": self.planner + self.locator,
                "blocked": self.blocked}


active_request_budget: ContextVar[RequestBudget | None] = ContextVar(
    "active_request_budget", default=None)
