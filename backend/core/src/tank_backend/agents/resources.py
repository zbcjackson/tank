"""Same-event-loop desktop exclusion for Runner-managed tasks."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol


class DesktopCleanup(Protocol):
    async def begin(self) -> None: ...
    async def finish(self) -> dict[str, Any]: ...


class DesktopResource:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self._quarantine: str | None = None

    def quarantine(self, reason: str) -> None:
        self._quarantine = reason

    def clear_quarantine(self) -> None:
        """Call only after an operator has verified input/process cleanup."""
        self._quarantine = None

    @asynccontextmanager
    async def acquire(self, deadline: float | None = None) -> AsyncIterator[None]:
        remaining = None if deadline is None else max(0, deadline - time.monotonic())
        await asyncio.wait_for(self.lock.acquire(), timeout=remaining)
        try:
            if self._quarantine is not None:
                raise RuntimeError(f"desktop quarantined: {self._quarantine}")
            yield
        finally:
            self.lock.release()


DESKTOP_RESOURCE = DesktopResource()
