"""Do not abandon native desktop work when its asyncio caller is cancelled."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


async def join_on_cancel(work: Awaitable[T]) -> T:
    task = asyncio.ensure_future(work)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Repeated cancellation must not release the desktop while work still runs.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  # Retrieve failure while preserving caller cancellation.
        raise


async def run_native(function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    return await join_on_cancel(asyncio.to_thread(function, *args, **kwargs))
