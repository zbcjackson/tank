"""Composition root — single source of truth for app-level dependencies.

Modules call ``deps.connection_manager()`` or ``deps.app_context()`` instead
of maintaining their own setter/getter pairs.  The internal container is a
mutable dict to avoid ``global`` reassignment (PLW0603).

To swap in a third-party IoC container later, replace the internals of this
module — consumers stay unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from ..channels.store import ChannelStore
    from ..config.context import AppContext
    from ..context.store import ConversationStore
    from ..jobs.scheduler import CronScheduler
    from ..jobs.store import JobStore
    from .manager import ConnectionManager

# ---------------------------------------------------------------------------
# Internal container — mutable dict avoids `global` reassignment
# ---------------------------------------------------------------------------

_deps: dict[str, AppContext | None] = {"ctx": None}
_mgr: dict[str, ConnectionManager | None] = {"v": None}


# ---------------------------------------------------------------------------
# Initialisation — called once from server.py at startup
# ---------------------------------------------------------------------------

def init(ctx: AppContext, mgr: ConnectionManager) -> None:
    """Wire the composition root.  Called once during server bootstrap."""
    _deps["ctx"] = ctx
    _mgr["v"] = mgr


# ---------------------------------------------------------------------------
# Typed accessors
# ---------------------------------------------------------------------------

def app_context() -> AppContext:
    """Return the app-level ``AppContext`` singleton."""
    ctx = _deps["ctx"]
    if ctx is None:
        raise RuntimeError("AppContext not initialised — call deps.init() first")
    return ctx


def connection_manager() -> ConnectionManager:
    """Return the ``ConnectionManager`` singleton."""
    mgr = _mgr["v"]
    if mgr is None:
        raise RuntimeError("ConnectionManager not initialised — call deps.init() first")
    return mgr


# -- Convenience wrappers for the most common lookups -----------------------

def conversation_store() -> ConversationStore:
    """Return the conversation store, or raise 503 if unavailable."""
    s = app_context().conversation_store
    if s is None:
        raise HTTPException(503, "Conversation store not initialised")
    return s


def channel_store() -> ChannelStore:
    """Return the channel store, or raise 503 if unavailable."""
    s = app_context().channel_store
    if s is None:
        raise HTTPException(503, "Channel store not initialised")
    return s


def job_store() -> JobStore:
    """Return the job store, or raise 503 if unavailable."""
    s = app_context().job_store
    if s is None:
        raise HTTPException(503, "Job store not initialised")
    return s


def scheduler() -> CronScheduler:
    """Return the cron scheduler, or raise 503 if unavailable."""
    s = app_context().scheduler
    if s is None:
        raise HTTPException(503, "Scheduler not initialised")
    return s
