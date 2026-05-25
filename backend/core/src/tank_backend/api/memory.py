"""REST API for inspecting learned preferences and stored memory for a user."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..memory import MemoryConfig, MemoryService
from ..preferences import PreferenceStore
from . import deps

logger = logging.getLogger("MemoryRoutes")

router = APIRouter(prefix="/api/memory", tags=["memory"], redirect_slashes=False)


class MemoryResponse(BaseModel):
    """Aggregated memory view for one user.

    Surfaces all three sources Tank tracks:
    - ``pinned`` / ``learned`` from the file-backed PreferenceStore
    - ``facts`` from the mem0-backed MemoryService (single flat pool)
    """

    user_id: str
    pinned: list[str]
    learned: list[str]
    facts: list[str]


def _get_store() -> PreferenceStore | None:
    """Build a PreferenceStore from app config, or None if disabled."""
    cfg = deps.app_context().app_config.preferences
    if not cfg.enabled:
        return None
    base_dir = Path(cfg.base_dir or "~/.tank").expanduser()
    return PreferenceStore(base_dir, cfg.max_entries)


@router.get("/{user_id}")
async def get_user_memory(user_id: str) -> MemoryResponse:
    """Return everything Tank remembers about ``user_id``.

    Combines PreferenceStore (pinned + learned) with the mem0 fact pool
    in a single flat response. The endpoint degrades silently when the
    memory backend is disabled or fails — empty lists rather than 500.
    """
    store = _get_store()
    if store is None:
        raise HTTPException(status_code=503, detail="Preference store is disabled")
    pinned = store.list_pinned(user_id)
    all_entries = store.list_for_user(user_id)
    learned = [e for e in all_entries if e not in pinned]

    facts = await _fetch_facts(user_id)
    return MemoryResponse(
        user_id=user_id, pinned=pinned, learned=learned, facts=facts,
    )


async def _fetch_facts(user_id: str) -> list[str]:
    """Return all stored mem0 facts for ``user_id``.

    Returns an empty list when the memory service is disabled or the
    recall fails — the introspection endpoint should degrade silently
    rather than 500.
    """
    cfg = deps.app_context().app_config.memory
    if not cfg.enabled:
        return []

    try:
        profile = deps.app_context().app_config.get_llm_profile("default")
    except (KeyError, ValueError):
        return []

    resolved = MemoryConfig(
        enabled=True,
        db_path=cfg.db_path,
        llm_api_key=cfg.llm_api_key or profile.api_key,
        llm_base_url=cfg.llm_base_url or profile.base_url,
        llm_model=cfg.llm_model or "",
        embedding_api_key=cfg.embedding_api_key or "",
        embedding_base_url=cfg.embedding_base_url or "",
        embedding_model=cfg.embedding_model or "",
        search_limit=cfg.search_limit,
    )
    try:
        service = MemoryService(resolved)
    except Exception:
        logger.warning("MemoryService init failed for /api/memory", exc_info=True)
        return []

    try:
        return await service.get_all(user_id)
    except Exception:
        logger.warning("Memory recall failed for user=%s", user_id, exc_info=True)
        return []
