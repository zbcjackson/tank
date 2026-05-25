"""REST API for inspecting per-session context-budget usage."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import deps

logger = logging.getLogger("UsageRoutes")

router = APIRouter(prefix="/api/context", tags=["context"], redirect_slashes=False)


class UsageResponse(BaseModel):
    session_id: str
    conversation_id: str | None
    tokens_used: int
    budget: int
    context_window: int
    fill_pct: float
    last_compaction_at: str | None
    ineffective_count: int
    compaction_passes: int


class CompactRequest(BaseModel):
    focus: str | None = Field(
        default=None,
        description="Optional topic to bias the summary toward.",
    )


class CompactResponse(BaseModel):
    session_id: str
    tokens_before: int
    tokens_after: int
    focus: str | None


def _snapshot_to_response(session_id: str, snapshot: Any) -> UsageResponse:
    return UsageResponse(
        session_id=session_id,
        conversation_id=snapshot.conversation_id,
        tokens_used=snapshot.tokens_used,
        budget=snapshot.budget,
        context_window=snapshot.context_window,
        fill_pct=snapshot.fill_pct,
        last_compaction_at=snapshot.last_compaction_at,
        ineffective_count=snapshot.ineffective_count,
        compaction_passes=snapshot.compaction_passes,
    )


@router.get("/usage/{session_id}", response_model=UsageResponse)
async def get_session_usage(session_id: str) -> UsageResponse:
    """Return current context-budget usage for one session."""
    mgr = deps.connection_manager()
    assistant = mgr.get_assistant(session_id)
    if assistant is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    snapshot = assistant.brain._context.usage_snapshot()
    return _snapshot_to_response(session_id, snapshot)


@router.get("/usage", response_model=list[UsageResponse])
async def get_all_usage() -> list[UsageResponse]:
    """Return context-budget usage for all active sessions."""
    mgr = deps.connection_manager()
    out: list[UsageResponse] = []
    for sid, assistant in mgr.iter_sessions():
        snapshot = assistant.brain._context.usage_snapshot()
        out.append(_snapshot_to_response(sid, snapshot))
    return out


@router.post("/compact/{session_id}", response_model=CompactResponse)
async def compact_session(
    session_id: str, request: CompactRequest | None = None
) -> CompactResponse:
    """Force a context compaction for one session.

    When ``focus`` is provided the summarizer biases toward information
    related to that topic. Anti-thrashing guards are bypassed because
    the user explicitly asked for compaction.
    """
    mgr = deps.connection_manager()
    assistant = mgr.get_assistant(session_id)
    if assistant is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    ctx = assistant.brain._context
    focus = request.focus if request else None
    tokens_before = ctx.count_tokens()
    await ctx.compact(focus=focus)
    tokens_after = ctx.count_tokens()
    return CompactResponse(
        session_id=session_id,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        focus=focus,
    )
