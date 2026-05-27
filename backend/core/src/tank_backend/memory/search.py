"""HybridSearch — fuse mem0 vector recall with FTS5 keyword recall.

Tank's existing :class:`MemoryService` is vector-only (mem0 + chroma).
That misses exact-token matches: filenames, IDs, and CJK queries that
embedding models tokenise poorly. :class:`HybridSearch` runs both
strategies in parallel and fuses with reciprocal rank fusion (RRF).

The result is a single deduped, ranked list of strings — drop-in for
``MemoryService.recall``'s caller.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..persistence.conversation_messages_store import (
        ConversationMessagesStore,
    )
    from .service import MemoryService

logger = logging.getLogger(__name__)


HitSource = Literal["vector", "keyword"]


@dataclass(frozen=True)
class HybridHit:
    text: str
    source: HitSource
    score: float


_RRF_K = 60.0


class HybridSearch:
    """Vector + keyword fusion over mem0 + FTS5.

    Both strategies are queried concurrently. Results are deduped on a
    normalised text key, and the surviving rank is the **sum** of each
    strategy's RRF contribution — so a hit that lands in both lists
    outranks any one-strategy hit.
    """

    def __init__(
        self,
        *,
        memory: MemoryService | None,
        messages_store: ConversationMessagesStore | None,
        keyword_limit: int = 20,
    ) -> None:
        self._memory = memory
        self._messages_store = messages_store
        self._keyword_limit = keyword_limit

    async def search(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 5,
        conversation_id: str | None = None,
    ) -> list[HybridHit]:
        """Return up to ``limit`` deduped hits, fused via RRF."""
        if not query.strip():
            return []

        vector_task: asyncio.Future[list[str]] | None = None
        if self._memory is not None:
            vector_task = asyncio.ensure_future(
                self._safe_vector(user_id, query, limit),
            )

        keyword_hits: list[str] = []
        if self._messages_store is not None:
            keyword_hits = self._safe_keyword(query, conversation_id)

        vector_hits: list[str] = []
        if vector_task is not None:
            try:
                vector_hits = await vector_task
            except Exception:
                logger.debug(
                    "HybridSearch: vector recall failed", exc_info=True,
                )
                vector_hits = []

        return _fuse(vector_hits, keyword_hits, limit=limit)

    async def _safe_vector(
        self, user_id: str, query: str, limit: int,
    ) -> list[str]:
        if self._memory is None:
            return []
        try:
            return await self._memory.recall(user_id, query, limit)
        except Exception:
            logger.debug(
                "HybridSearch: vector recall raised", exc_info=True,
            )
            return []

    def _safe_keyword(
        self, query: str, conversation_id: str | None,
    ) -> list[str]:
        if self._messages_store is None:
            return []
        try:
            hits = self._messages_store.search(
                query,
                limit=self._keyword_limit,
                conversation_id=conversation_id,
            )
            return [h.content for h in hits]
        except Exception:
            logger.debug(
                "HybridSearch: keyword recall raised", exc_info=True,
            )
            return []


def _fuse(
    vector_hits: list[str],
    keyword_hits: list[str],
    *,
    limit: int,
) -> list[HybridHit]:
    """Reciprocal rank fusion across two ranked lists."""
    scores: dict[str, tuple[float, HitSource, str]] = {}

    for rank, text_val in enumerate(vector_hits, start=1):
        key = _normalise(text_val)
        if not key:
            continue
        score = 1.0 / (_RRF_K + rank)
        prev = scores.get(key)
        if prev is None:
            scores[key] = (score, "vector", text_val)
        else:
            # Already present from the other list — sum scores.
            scores[key] = (
                prev[0] + score,
                "vector" if prev[1] == "keyword" else prev[1],
                prev[2],
            )

    for rank, text_val in enumerate(keyword_hits, start=1):
        key = _normalise(text_val)
        if not key:
            continue
        score = 1.0 / (_RRF_K + rank)
        prev = scores.get(key)
        if prev is None:
            scores[key] = (score, "keyword", text_val)
        else:
            scores[key] = (
                prev[0] + score,
                # Preserve the "first-seen" surface form but mark
                # multi-strategy hits with the higher rank source.
                prev[1],
                prev[2],
            )

    fused = [
        HybridHit(text=payload[2], source=payload[1], score=payload[0])
        for payload in scores.values()
    ]
    fused.sort(key=lambda h: h.score, reverse=True)
    return fused[:limit]


_WS_RE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    return _WS_RE.sub(" ", text.strip().lower())
