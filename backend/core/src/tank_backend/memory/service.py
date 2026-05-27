"""MemoryService — async-safe wrapper around mem0 for Tank's voice pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..config.models import MemoryConfig

if TYPE_CHECKING:
    from .search import HybridSearch

logger = logging.getLogger(__name__)


class MemoryService:
    """Persistent cross-session memory layer using mem0.

    All mem0 operations are synchronous under the hood, so this service
    wraps every call in ``asyncio.to_thread()`` to avoid blocking the
    event loop or the real-time voice pipeline.
    """

    def __init__(self, config: MemoryConfig) -> None:
        self._config = config
        self._mem = self._create_memory(config)
        self._hybrid: HybridSearch | None = None

    def attach_hybrid_search(self, hybrid: HybridSearch | None) -> None:
        """Optionally route ``recall`` through hybrid (vector + keyword) search.

        When attached, ``recall`` returns the fused list. ``store_turn``
        and ``get_all`` are unchanged — they still go straight to mem0.
        """
        self._hybrid = hybrid

    async def store_turn(
        self,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Extract and store facts from a conversation turn.

        Runs in a thread pool so it never blocks the pipeline.
        """
        messages = [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
        await asyncio.to_thread(
            self._mem.add,
            messages,
            user_id=user_id,
        )
        logger.debug("Memory stored for user %s", user_id)

    async def recall(
        self,
        user_id: str,
        query: str,
        limit: int | None = None,
    ) -> list[str]:
        """Retrieve relevant memories for context injection.

        Returns a list of plain-text memory strings, most relevant first.
        When a :class:`HybridSearch` orchestrator is attached, fuses
        vector results with FTS5 keyword hits via RRF.
        """
        search_limit = limit or self._config.search_limit
        if self._hybrid is not None:
            hits = await self._hybrid.search(
                user_id=user_id, query=query, limit=search_limit,
            )
            return [h.text for h in hits]
        return await self._vector_recall(user_id, query, search_limit)

    async def _vector_recall(
        self, user_id: str, query: str, limit: int,
    ) -> list[str]:
        """Pure mem0 vector search — no hybrid fusion.

        Called from :meth:`recall` when no hybrid is attached, **and**
        from :class:`HybridSearch._safe_vector` to obtain the vector
        leg of the fusion. ``HybridSearch`` calls this directly to
        avoid recursing back through :meth:`recall`.
        """
        result = await asyncio.to_thread(
            self._mem.search,
            query=query,
            user_id=user_id,
            limit=limit,
        )
        memories: list[dict[str, Any]] = result.get("results", [])
        return _extract_memory_texts(memories)

    async def get_all(self, user_id: str) -> list[str]:
        """Return every memory for a user (debugging / admin)."""
        result = await asyncio.to_thread(self._mem.get_all, user_id=user_id)
        memories: list[dict[str, Any]] = result.get("results", [])
        return _extract_memory_texts(memories)

    @staticmethod
    def _create_memory(config: MemoryConfig) -> Any:
        """Build a mem0 ``Memory`` instance from Tank config."""
        from mem0 import Memory

        db_path = Path(config.db_path)
        db_path.mkdir(parents=True, exist_ok=True)

        mem0_config: dict[str, Any] = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "tank_memory",
                    "path": str(db_path),
                },
            },
        }

        if config.llm_api_key:
            llm_cfg: dict[str, Any] = {
                "provider": "openai",
                "config": {
                    "api_key": config.llm_api_key,
                },
            }
            if config.llm_model:
                llm_cfg["config"]["model"] = config.llm_model
            if config.llm_base_url:
                llm_cfg["config"]["openai_base_url"] = config.llm_base_url
            mem0_config["llm"] = llm_cfg

        embed_api_key = config.embedding_api_key or config.llm_api_key
        if embed_api_key:
            embedder_cfg: dict[str, Any] = {
                "provider": "openai",
                "config": {
                    "api_key": embed_api_key,
                },
            }
            embed_base_url = config.embedding_base_url or config.llm_base_url
            if embed_base_url:
                embedder_cfg["config"]["openai_base_url"] = embed_base_url
            if config.embedding_model:
                embedder_cfg["config"]["model"] = config.embedding_model
            mem0_config["embedder"] = embedder_cfg

        history_path = db_path / "history.db"
        mem0_config["history_db_path"] = str(history_path)

        return Memory.from_config(mem0_config)


def _extract_memory_texts(memories: list[dict[str, Any]]) -> list[str]:
    """Pull non-empty memory strings out of mem0 result entries."""
    out: list[str] = []
    for m in memories:
        text = m.get("memory")
        if text:
            out.append(text)
    return out
