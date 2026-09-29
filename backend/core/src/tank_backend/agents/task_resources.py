"""Bounded, idempotent cleanup of task-owned resources and borrowed leases."""

import asyncio
import math
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .subagent import SubAgentCleanupError, SubAgentStopped

Result = TypeVar("Result")


class TaskResources:
    def __init__(self, timeout: float = 5.0) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("cleanup timeout must be finite and positive")
        self._timeout = timeout
        self._releases: dict[str, Callable[[], Awaitable[None]]] = {}
        self._closing: asyncio.Task[None] | None = None

    def own(self, name: str, release: Callable[[], Awaitable[None]]) -> None:
        """For borrowed resources register detach, never the owner's close callback."""
        if self._closing is not None:
            raise SubAgentStopped("runtime_closed")
        if not name or len(name) > 128 or name in self._releases or len(self._releases) >= 32:
            raise ValueError("invalid resource registration")
        self._releases[name] = release

    async def aclose(self) -> None:
        if self._closing is None:
            self._closing = asyncio.create_task(self._close())
            self._closing.add_done_callback(consume_exception)
        await asyncio.shield(self._closing)

    async def _close(self) -> None:
        failures: list[str] = []
        timeout = self._timeout / max(1, len(self._releases))
        for name, release in reversed(self._releases.items()):
            try:
                operation = asyncio.ensure_future(release())
                done, _ = await asyncio.wait({operation}, timeout=timeout)
                if not done:
                    operation.cancel()
                    operation.add_done_callback(consume_exception)
                    raise TimeoutError("resource cleanup deadline")
                operation.result()
            except (Exception, asyncio.CancelledError):
                failures.append(name)
        if failures:
            raise SubAgentCleanupError("Task resource cleanup unconfirmed: " + ", ".join(failures))


def consume_exception(operation: asyncio.Future[Result]) -> None:
    """Timed-out cooperative callbacks may finish after the task was quarantined."""
    if not operation.cancelled():
        operation.exception()
