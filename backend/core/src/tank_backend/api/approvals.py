"""REST API routes for approval management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .manager import SessionManager

logger = logging.getLogger("ApprovalRoutes")

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

# Will be set by server.py when registering routes
_session_manager: SessionManager | None = None


def set_session_manager(manager: SessionManager) -> None:
    """Set the shared session manager reference."""
    global _session_manager  # noqa: PLW0603
    _session_manager = manager


class ApprovalResponse(BaseModel):
    """Body for responding to an approval request."""
    approved: bool
    reason: str = ""


@router.post("/{approval_id}/respond")
async def respond_to_approval(approval_id: str, body: ApprovalResponse):
    """Approve or reject a pending tool execution request."""
    if _session_manager is None:
        raise HTTPException(503, "Service not initialized")

    # Search all sessions for the approval manager with this pending approval
    for _session_id, assistant in _session_manager.iter_sessions():
        mgr = assistant.approval_manager
        if mgr is None:
            continue
        pending = mgr.get_pending()
        if any(p.approval_id == approval_id for p in pending):
            resolved = mgr.resolve(approval_id, approved=body.approved, reason=body.reason)
            if resolved:
                return {
                    "status": "ok",
                    "approval_id": approval_id,
                    "approved": body.approved,
                }
            raise HTTPException(409, f"Approval {approval_id} already resolved")

    raise HTTPException(404, f"Approval {approval_id} not found")


@router.get("")
async def list_pending_approvals(session_id: str | None = None):
    """List pending approval requests, optionally filtered by session."""
    if _session_manager is None:
        raise HTTPException(503, "Service not initialized")

    all_pending = []
    for sid, assistant in _session_manager.iter_sessions():
        if session_id and sid != session_id:
            continue
        mgr = assistant.approval_manager
        if mgr is None:
            continue
        for req in mgr.get_pending(session_id=sid):
            all_pending.append({
                "approval_id": req.approval_id,
                "tool_name": req.tool_name,
                "tool_args": req.tool_args,
                "description": req.description,
                "session_id": req.session_id,
            })

    return {"pending": all_pending}
