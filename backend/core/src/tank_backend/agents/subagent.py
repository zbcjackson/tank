"""Supplier-independent contract for task-oriented plugin agents."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import JsonValue

from ..core.token_usage import TokenUsageLedger
from .base import AgentOutput

if TYPE_CHECKING:
    from .task_result import TaskResult
    from .task_runtime import ExecutionRecord, TaskRuntime


def validate_task_input(value: object) -> dict[str, JsonValue] | None:
    """Detach a bounded JSON object; domain validation belongs to the plugin."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("task_input must be a JSON object")

    def copy_value(item: object, depth: int) -> JsonValue:
        if depth > 16:
            raise ValueError("task_input exceeds 16 levels of nesting")
        if item is None or isinstance(item, (str, bool, int)):
            return item
        if isinstance(item, float) and math.isfinite(item):
            return item
        if isinstance(item, list):
            return [copy_value(child, depth + 1) for child in item]
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            return {key: copy_value(child, depth + 1) for key, child in item.items()}
        raise ValueError("task_input must contain only JSON values and string keys")

    result = copy_value(value, 0)
    assert isinstance(result, dict)
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    try:
        size = len(encoded.encode("utf-8"))
    except UnicodeError as exc:
        raise ValueError("task_input must contain valid UTF-8 text") from exc
    if size > 64 * 1024:
        raise ValueError("task_input exceeds 65536 UTF-8 bytes")
    return result


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

    def __init__(self, detail: str, task_result: TaskResult | None = None) -> None:
        self.task_result = task_result.with_cleanup("unknown") if task_result is not None else None
        super().__init__(detail)


class SubAgentCancelled(asyncio.CancelledError):
    """Cancellation after cleanup, retaining any already-received task evidence."""

    def __init__(self, task_result: TaskResult | None = None) -> None:
        self.task_result = task_result
        super().__init__("subagent cancellation requested")


@dataclass(frozen=True)
class SubAgentRequest:
    task: str
    context: str
    task_id: str
    task_input: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_input", validate_task_input(self.task_input))


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
class SubAgentBudget(TokenUsageLedger):
    """Usage accounting with an opt-in legacy task limit; zero means record only."""

    limit: int = 0

    def check(self) -> None:
        if self.limit > 0 and self.unknown_calls:
            raise SubAgentStopped("budget", "usage unknown")
        if self.limit > 0 and self.total_tokens >= self.limit:
            raise SubAgentStopped(
                "budget", f"token budget ({self.total_tokens}/{self.limit} tokens)",
            )


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
    audit: Callable[[ExecutionRecord], Awaitable[None]] | None = None
    runtime: TaskRuntime = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        from .task_runtime import TaskRuntime

        object.__setattr__(self, "runtime", TaskRuntime(self, audit=self.audit))

    def check(self, permission: str | None = None) -> None:
        self.runtime.check_open()
        self.authorization.check(permission)
        if self.cancel.is_set():
            raise asyncio.CancelledError("subagent cancellation requested")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError("subagent deadline exceeded")
        self.budget.check()

    def observe(self, kind: str, **metadata: Any) -> None:
        if self.observer is not None:
            try:
                self.observer.on_event(kind, metadata)
            except Exception:
                logging.getLogger(__name__).warning("Subagent observer failed for %s", kind)


class SubAgent(ABC):
    capabilities = SubAgentCapabilities()

    @abstractmethod
    def run(self, request: SubAgentRequest, context: SubAgentContext) -> AsyncIterator[AgentOutput]:
        raise NotImplementedError

    @abstractmethod
    async def aclose(self) -> None:
        """Close owned resources, or raise if cleanup is not confirmed."""
        raise NotImplementedError
