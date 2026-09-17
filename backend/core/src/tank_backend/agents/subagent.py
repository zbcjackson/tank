"""Supplier-independent contract for task-oriented plugin agents."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from .base import AgentOutput


class SubAgentStopped(RuntimeError):
    """A controlled, incomplete termination."""

    def __init__(
        self, reason: str, detail: str = "", metadata: dict[str, Any] | None = None
    ) -> None:
        self.reason = reason
        self.metadata = metadata or {}
        super().__init__(f"{reason}: {detail}" if detail else reason)


class SubAgentCleanupError(RuntimeError):
    """Cleanup could not be confirmed; a desktop must be quarantined."""


@dataclass(frozen=True)
class SubAgentRequest:
    task: str
    context: str
    task_id: str


@dataclass(frozen=True)
class SubAgentCapabilities:
    cancel: bool = False
    pause: bool = False
    resume: bool = False
    persistent_resume: bool = False
    pause_boundary: str = "unsupported"


@dataclass
class SubAgentAuthorization:
    """Task-level grant, issued by Tank, revocable at action boundaries."""

    permissions: frozenset[str] = frozenset()
    active: bool = True

    def revoke(self) -> None:
        self.active = False

    def check(self, permission: str | None = None) -> None:
        if not self.active or (permission and permission not in self.permissions):
            raise SubAgentStopped("error", f"authorization required: {permission or 'revoked'}")


@dataclass
class SubAgentBudget:
    """One shared ledger; event observers never own accounting."""

    limit: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    call_ids: set[str] = field(default_factory=set)
    unknown_calls: set[str] = field(default_factory=set)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def record(self, call_id: str, prompt_tokens: int, completion_tokens: int) -> None:
        if call_id in self.call_ids:
            return
        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("usage must be non-negative")
        self.call_ids.add(call_id)
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens

    def record_unknown(self, call_id: str) -> None:
        self.unknown_calls.add(call_id)

    def check(self) -> None:
        if self.limit > 0 and self.unknown_calls:
            raise SubAgentStopped("budget", "usage unknown")
        if self.limit > 0 and self.total_tokens >= self.limit:
            raise SubAgentStopped("budget", f"{self.total_tokens}/{self.limit} tokens")


class SubAgentObserver(Protocol):
    def on_event(self, kind: str, metadata: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class SubAgentContext:
    authorization: SubAgentAuthorization
    budget: SubAgentBudget
    cancel: asyncio.Event
    deadline: float | None = None
    observer: SubAgentObserver | None = None
    max_steps: int | None = None

    def check(self, permission: str | None = None) -> None:
        self.authorization.check(permission)
        if self.cancel.is_set():
            raise asyncio.CancelledError("subagent cancellation requested")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError("subagent deadline exceeded")
        self.budget.check()

    def observe(self, kind: str, **metadata: Any) -> None:
        if self.observer is not None:
            self.observer.on_event(kind, metadata)


class SubAgent(ABC):
    capabilities = SubAgentCapabilities()

    @abstractmethod
    def run(self, request: SubAgentRequest, context: SubAgentContext) -> AsyncIterator[AgentOutput]:
        raise NotImplementedError

    @abstractmethod
    async def aclose(self) -> None:
        """Close owned resources, or raise if cleanup is not confirmed."""
        raise NotImplementedError
