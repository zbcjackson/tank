"""Agents (workers) REST API.

Phase 2 step 6 of the workflow & orchestration roadmap. Read-only
endpoints today — list active workers and inspect a single worker by
``task_id``.

Cancellation is intentionally NOT exposed here. Each ``Assistant``
owns its own ``WorkerSupervisor``, so the in-process task references
needed for ``stop`` are session-scoped. The ``agent_stop`` tool (and
the web UI invoking it through chat) covers cancellation today; a
multi-session router could land later if direct REST cancel becomes
necessary.

The companion ``WorkerInboxObserver`` already surfaces terminal
completions back into the originating conversation, so the typical
client doesn't need to poll. These routes are for the "running tasks"
panel in the web UI.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from ..agents.store import WorkerRun
from . import deps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"], redirect_slashes=False)


def _run_to_dict(run: WorkerRun, *, include_output: bool = True) -> dict[str, Any]:
    """JSON shape for a single worker run."""
    data: dict[str, Any] = {
        "task_id": run.task_id,
        "agent_def": run.agent_def,
        "description": run.description,
        "status": run.status,
        "background": run.background,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "originating_conversation_id": run.originating_conversation_id,
        "originating_channel": run.originating_channel,
    }
    if include_output:
        data["output"] = run.output
        data["error"] = run.error
    return data


@router.get("")
async def list_agents(
    conversation_id: str | None = None,
    include_terminal: bool = False,
) -> list[dict[str, Any]]:
    """List worker runs.

    Defaults to the active set (status=running). Pass
    ``conversation_id`` to scope to one conversation, or
    ``include_terminal=true`` to also include
    completed/failed/cancelled/timeout. ``conversation_id`` is the
    routing key the inbox observer uses, so it survives reconnects.
    """
    store = deps.worker_store()
    if conversation_id is not None:
        runs = store.list_for_conversation(
            conversation_id, include_terminal=include_terminal,
        )
    else:
        runs = store.list_active()
    return [_run_to_dict(r, include_output=False) for r in runs]


@router.get("/{task_id}")
async def get_agent(task_id: str) -> dict[str, Any]:
    """Get full details (including output and error) for a single run."""
    store = deps.worker_store()
    run = store.get(task_id)
    if run is None:
        raise HTTPException(404, f"task_id '{task_id}' not found")
    return _run_to_dict(run)
