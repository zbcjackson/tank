"""Tests for memory.search — HybridSearch fusion."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from tank_backend.memory.search import HybridHit, HybridSearch
from tank_backend.persistence.conversation_messages_store import (
    ConversationMessageHit,
)


def _kw_hit(text: str, rank: float = -1.0) -> ConversationMessageHit:
    return ConversationMessageHit(
        conversation_id="conv-1",
        seq=0,
        role="user",
        content=text,
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
        rank=rank,
    )


class TestHybridSearch:
    async def test_empty_query_returns_empty(self):
        memory = MagicMock()
        memory.recall = AsyncMock()
        messages_store = MagicMock()

        hs = HybridSearch(memory=memory, messages_store=messages_store)
        result = await hs.search(user_id="u", query="   ", limit=5)

        assert result == []
        memory.recall.assert_not_called()
        messages_store.search.assert_not_called()

    async def test_vector_only_when_messages_store_absent(self):
        memory = MagicMock()
        memory.recall = AsyncMock(return_value=["fact one", "fact two"])

        hs = HybridSearch(memory=memory, messages_store=None)
        result = await hs.search(user_id="u", query="something", limit=5)

        assert [h.text for h in result] == ["fact one", "fact two"]
        assert all(h.source == "vector" for h in result)

    async def test_keyword_only_when_memory_absent(self):
        messages_store = MagicMock()
        messages_store.search = MagicMock(return_value=[
            _kw_hit("kw hit 1"),
            _kw_hit("kw hit 2"),
        ])

        hs = HybridSearch(memory=None, messages_store=messages_store)
        result = await hs.search(user_id="u", query="alpha", limit=5)

        assert [h.text for h in result] == ["kw hit 1", "kw hit 2"]
        assert all(h.source == "keyword" for h in result)

    async def test_fusion_promotes_dual_hits(self):
        memory = MagicMock()
        memory.recall = AsyncMock(return_value=["A", "B", "C"])
        messages_store = MagicMock()
        messages_store.search = MagicMock(return_value=[
            _kw_hit("B"), _kw_hit("D"),
        ])

        hs = HybridSearch(memory=memory, messages_store=messages_store)
        result = await hs.search(user_id="u", query="x", limit=10)

        texts = [h.text for h in result]
        # "B" appears in both lists → sum of RRF scores → should rank
        # ahead of single-list hits.
        assert texts[0] == "B"
        # All four unique texts should be present.
        assert set(texts) == {"A", "B", "C", "D"}

    async def test_dedupes_whitespace_and_case(self):
        memory = MagicMock()
        memory.recall = AsyncMock(return_value=["Hello World"])
        messages_store = MagicMock()
        messages_store.search = MagicMock(return_value=[
            _kw_hit("hello   world"),
            _kw_hit("totally different"),
        ])

        hs = HybridSearch(memory=memory, messages_store=messages_store)
        result = await hs.search(user_id="u", query="x", limit=10)

        # Whitespace-normalised, case-folded match → only one entry.
        texts = [h.text for h in result]
        assert "totally different" in texts
        # Deduped: "Hello World" / "hello world" collapse to one row.
        normalised_count = sum(
            1 for t in texts if t.lower().strip() == "hello world"
        )
        assert normalised_count == 1

    async def test_limit_applied_after_fusion(self):
        memory = MagicMock()
        memory.recall = AsyncMock(return_value=[
            "v1", "v2", "v3", "v4", "v5",
        ])
        messages_store = MagicMock()
        messages_store.search = MagicMock(return_value=[
            _kw_hit("k1"), _kw_hit("k2"),
        ])

        hs = HybridSearch(memory=memory, messages_store=messages_store)
        result = await hs.search(user_id="u", query="x", limit=3)

        assert len(result) == 3

    async def test_vector_failure_falls_back_to_keyword(self):
        memory = MagicMock()
        memory.recall = AsyncMock(side_effect=RuntimeError("mem0 down"))
        messages_store = MagicMock()
        messages_store.search = MagicMock(return_value=[_kw_hit("kw")])

        hs = HybridSearch(memory=memory, messages_store=messages_store)
        result = await hs.search(user_id="u", query="x", limit=5)

        assert [h.text for h in result] == ["kw"]

    async def test_keyword_failure_falls_back_to_vector(self):
        memory = MagicMock()
        memory.recall = AsyncMock(return_value=["v1", "v2"])
        messages_store = MagicMock()
        messages_store.search = MagicMock(side_effect=RuntimeError("fts boom"))

        hs = HybridSearch(memory=memory, messages_store=messages_store)
        result = await hs.search(user_id="u", query="x", limit=5)

        assert [h.text for h in result] == ["v1", "v2"]

    async def test_both_failing_returns_empty(self):
        memory = MagicMock()
        memory.recall = AsyncMock(side_effect=RuntimeError("a"))
        messages_store = MagicMock()
        messages_store.search = MagicMock(side_effect=RuntimeError("b"))

        hs = HybridSearch(memory=memory, messages_store=messages_store)
        result = await hs.search(user_id="u", query="x", limit=5)

        assert result == []


class TestHybridHit:
    def test_fields(self):
        h = HybridHit(text="x", source="vector", score=0.5)
        assert h.text == "x"
        assert h.source == "vector"
        assert h.score == 0.5
