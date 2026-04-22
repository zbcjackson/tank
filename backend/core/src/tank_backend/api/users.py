"""REST API routes for user management — reads from speaker DB."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..users import UserManager
from .manager import ConnectionManager

logger = logging.getLogger("UserRoutes")

router = APIRouter(prefix="/api/users", tags=["users"], redirect_slashes=False)

# Follows the same DI pattern as speakers.py, approvals.py, etc.
_connection_manager: ConnectionManager | None = None


def set_connection_manager(manager: ConnectionManager) -> None:
    """Set the shared connection manager reference."""
    global _connection_manager  # noqa: PLW0603
    _connection_manager = manager


def _get_user_manager() -> UserManager:
    """Build a UserManager from the shared ConnectionManager."""
    if _connection_manager is None:
        raise HTTPException(503, "User service not initialized")
    recognizer = _connection_manager.get_voiceprint_recognizer()
    repo = recognizer.repository if recognizer and recognizer.enabled else None
    return UserManager(repo, Path.home() / ".tank" / "users")


# ------------------------------------------------------------------
# Response model
# ------------------------------------------------------------------


class UserResponse(BaseModel):
    user_id: str
    name: str
    sample_count: int


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("", response_model=list[UserResponse])
async def list_users():
    """List all users (from speaker DB)."""
    mgr = _get_user_manager()
    return [
        UserResponse(user_id=u.user_id, name=u.name, sample_count=u.sample_count)
        for u in mgr.list_users()
    ]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    """Get user by ID."""
    mgr = _get_user_manager()
    user = mgr.get_user(user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return UserResponse(user_id=user.user_id, name=user.name, sample_count=user.sample_count)


@router.delete("/{user_id}")
async def delete_user(user_id: str):
    """Delete user from speaker DB and remove user folder."""
    mgr = _get_user_manager()
    deleted = mgr.delete_user(user_id)
    if not deleted:
        raise HTTPException(404, "User not found")
    return {"status": "deleted", "user_id": user_id}
