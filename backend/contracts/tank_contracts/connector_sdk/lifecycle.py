"""Background-task lifecycle helper for connector plugins.

Every connector runs one long-lived background task — Telegram's poll
loop, Slack's Socket-Mode WebSocket, Discord's gateway connection. All
three today hand-roll the same shutdown choreography:

1. Signal the platform loop to exit (platform-specific; not our
   concern).
2. Wait up to N seconds for the task to drain on its own.
3. If it doesn't, cancel the task and swallow the resulting
   :class:`asyncio.CancelledError`.
4. Log loudly on any unexpected exception so a silent-death connector
   doesn't leave operators guessing why their bot stopped responding.

This module centralises steps 2-4. Plugins keep owning step 1 because
each platform signals shutdown through a different SDK call.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class BackgroundTaskRunner:
    """Owns one long-running ``asyncio.Task`` with graceful shutdown.

    Usage::

        self._runner = BackgroundTaskRunner(
            instance_name=self.instance_name,
            platform=self.platform,
            shutdown_timeout_s=5.0,
        )

        # in start():
        self._runner.spawn(self._run_platform_loop())

        # in stop():
        # ... signal the platform loop to exit (SDK-specific) ...
        await self._runner.drain()

    The runner is single-use per ``spawn``: after ``drain`` returns,
    call ``spawn`` again to start a fresh task. ``drain`` before
    ``spawn`` (and ``drain`` after a prior ``drain``) are both no-ops.

    Thread-safety: the runner is designed for use from a single event
    loop — the same loop that owns the spawned task. Multi-thread
    callers should coordinate externally.
    """

    def __init__(
        self,
        *,
        instance_name: str,
        platform: str,
        shutdown_timeout_s: float = 5.0,
    ) -> None:
        self._instance_name = instance_name
        self._platform = platform
        self._shutdown_timeout_s = shutdown_timeout_s
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """True when a task exists and hasn't finished yet.

        After ``drain`` returns, the task reference is cleared and this
        property flips to False — mirroring the plugins' existing
        ``_task is not None`` checks.
        """
        return self._task is not None and not self._task.done()

    def spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """Start ``coro`` as a background task.

        The wrapper catches unexpected exceptions and logs them — a
        crashing platform loop is otherwise silent (the event loop
        surfaces the error only on garbage-collection, which may be
        hours later). :class:`asyncio.CancelledError` is re-raised
        rather than swallowed so ``asyncio.wait_for`` + ``cancel``
        semantics work as expected in ``drain``.

        Returns the created task so callers can attach further
        callbacks if needed. In practice every plugin just stores the
        task as ``self._task`` and never touches it directly after —
        the runner owns the lifecycle from here.

        Calling :meth:`spawn` while a task is still running raises
        :class:`RuntimeError`. That matches the plugins' existing
        ``if self._connected: return`` idioms: the runner makes the
        double-start error loud instead of silent.
        """
        if self.running:
            raise RuntimeError(
                f"{self._platform} connector '{self._instance_name}': "
                "BackgroundTaskRunner.spawn called while prior task is "
                "still running",
            )

        task_name = f"{self._platform}-bg-{self._instance_name}"
        self._task = asyncio.create_task(
            self._wrap(coro), name=task_name,
        )
        return self._task

    async def _wrap(self, coro: Coroutine[Any, Any, None]) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "%s connector '%s' background task crashed",
                self._platform, self._instance_name,
            )
            raise

    async def drain(self) -> None:
        """Wait up to ``shutdown_timeout_s`` for the task to finish,
        then cancel it if it hasn't.

        Safe to call multiple times; subsequent calls after the first
        return immediately. Safe to call when no task has ever been
        spawned.

        Any exception the task raised during its natural lifetime is
        logged (by :meth:`_wrap`) rather than re-raised — shutdown
        shouldn't propagate the child's crash, because at this point
        the process is already on its way down.
        """
        task = self._task
        if task is None:
            return
        # Clear the reference up-front so concurrent/repeat drains are
        # effectively idempotent — whichever caller wins the race owns
        # the wait, the rest short-circuit.
        self._task = None

        if task.done():
            # The task may have already finished during platform-specific
            # signal-to-exit work. Retrieve its exception (if any) to
            # suppress unhandled-exception warnings, then return.
            with contextlib.suppress(
                asyncio.CancelledError, Exception,
            ):
                task.result()
            return

        try:
            await asyncio.wait_for(task, timeout=self._shutdown_timeout_s)
        except asyncio.TimeoutError:
            logger.warning(
                "%s connector '%s' task did not exit in %.1fs; cancelling",
                self._platform, self._instance_name,
                self._shutdown_timeout_s,
            )
            task.cancel()
            with contextlib.suppress(
                asyncio.CancelledError,
                asyncio.TimeoutError,
                Exception,
            ):
                await task
        except asyncio.CancelledError:
            # Task was cancelled externally; the wait completes with
            # the cancellation and we're done.
            raise
        except Exception:
            # _wrap already logged the traceback; we swallow here so
            # plugin ``stop`` methods stay clean.
            logger.debug(
                "%s connector '%s' task raised during drain (already logged)",
                self._platform, self._instance_name,
                exc_info=True,
            )


__all__ = ["BackgroundTaskRunner"]
