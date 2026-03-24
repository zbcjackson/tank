"""MemoryService — async-safe wrapper around mem0 for Tank's voice pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from .config import MemoryConfig

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

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

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
        await asyncio.to_thread(self._mem.add, messages, user_id=user_id)
        logger.debug("Memory stored for user %s", user_id)

    async def recall(
        self,
        user_id: str,
        query: str,
        limit: int | None = None,
    ) -> list[str]:
        """Retrieve relevant memories for context injection.

        Returns a list of plain-text memory strings, most relevant first.
        """
        search_limit = limit or self._config.search_limit
        result = await asyncio.to_thread(
            self._mem.search,
            query=query,
            user_id=user_id,
            limit=search_limit,
        )
        memories: list[dict[str, Any]] = result.get("results", [])
        return [m["memory"] for m in memories if m.get("memory")]

    async def get_all(self, user_id: str) -> list[str]:
        """Return every memory for a user (debugging / admin)."""
        result = await asyncio.to_thread(self._mem.get_all, user_id=user_id)
        memories: list[dict[str, Any]] = result.get("results", [])
        return [m["memory"] for m in memories if m.get("memory")]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _create_memory(config: MemoryConfig) -> Any:
        """Build a mem0 ``Memory`` instance from Tank config."""
        from mem0 import Memory

        # Ensure the ChromaDB directory exists
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

        # LLM — reuse Tank's existing OpenAI-compatible provider
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

            # Embedder — same API key, default embedding model
            embedder_cfg: dict[str, Any] = {
                "provider": "openai",
                "config": {
                    "api_key": config.llm_api_key,
                },
            }
            if config.llm_base_url:
                embedder_cfg["config"]["openai_base_url"] = config.llm_base_url
            mem0_config["embedder"] = embedder_cfg

        # History DB alongside the vector store
        history_path = db_path / "history.db"
        mem0_config["history_db_path"] = str(history_path)

        return Memory.from_config(mem0_config)
