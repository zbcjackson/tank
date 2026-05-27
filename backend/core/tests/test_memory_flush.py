"""Tests for memory.flush — MemoryFlusher pre-compaction extractor."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from tank_backend.memory.flush import (
    FlushDecision,
    FlushResult,
    MemoryFlusher,
)


def _make_flusher(
    *,
    llm: AsyncMock | None = None,
    memory: MagicMock | None = None,
    preferences: MagicMock | None = None,
    timeout_seconds: float = 8.0,
) -> tuple[MemoryFlusher, AsyncMock, MagicMock, MagicMock]:
    if llm is None:
        llm = AsyncMock()
    if memory is None:
        memory = MagicMock()
        memory.store_turn = AsyncMock()
    if preferences is None:
        preferences = MagicMock()
        preferences.reinforce = MagicMock(return_value=True)
    flusher = MemoryFlusher(
        llm=llm,
        memory=memory,
        preferences=preferences,
        timeout_seconds=timeout_seconds,
    )
    return flusher, llm, memory, preferences


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


class TestFlushHappyPath:
    async def test_returns_parsed_categories(self):
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({
            "facts_to_remember": ["Lives in Berlin"],
            "preferences_to_reinforce": ["Prefers metric units"],
            "decisions": [{"what": "Use Postgres", "why": "Existing infra"}],
        })
        flusher, _, _, _ = _make_flusher(llm=llm)

        result = await flusher.flush(
            user="jackson",
            messages=[_msg("user", "I'm in Berlin"),
                      _msg("assistant", "Good to know.")],
        )

        assert result.facts_to_remember == ["Lives in Berlin"]
        assert result.preferences_to_reinforce == ["Prefers metric units"]
        assert result.decisions == [
            FlushDecision(what="Use Postgres", why="Existing infra"),
        ]

    async def test_routes_facts_to_memory(self):
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({
            "facts_to_remember": ["Lives in Berlin", "Owns a Tesla"],
            "preferences_to_reinforce": [],
            "decisions": [],
        })
        flusher, _, memory, _ = _make_flusher(llm=llm)

        await flusher.flush(
            user="jackson",
            messages=[_msg("user", "hi")],
        )

        # Drain any background tasks the flusher started.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        calls = memory.store_turn.await_args_list
        called_facts = sorted(call.args[1] for call in calls)
        assert called_facts == ["Lives in Berlin", "Owns a Tesla"]
        assert all(call.args[0] == "jackson" for call in calls)

    async def test_routes_preferences_to_reinforce(self):
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({
            "facts_to_remember": [],
            "preferences_to_reinforce": ["Prefers metric units"],
            "decisions": [],
        })
        flusher, _, _, prefs = _make_flusher(llm=llm)

        await flusher.flush(
            user="jackson",
            messages=[_msg("user", "use celsius")],
        )

        prefs.reinforce.assert_called_once_with(
            "jackson", "Prefers metric units",
        )

    async def test_routes_decisions_with_rationale(self):
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({
            "facts_to_remember": [],
            "preferences_to_reinforce": [],
            "decisions": [{"what": "Use Postgres", "why": "Existing infra"}],
        })
        flusher, _, memory, _ = _make_flusher(llm=llm)

        await flusher.flush(user="jackson", messages=[_msg("user", "x")])
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        memory.store_turn.assert_awaited_once_with(
            "jackson", "Use Postgres — because Existing infra", "",
        )


class TestFlushShortCircuits:
    async def test_guest_user_skipped(self):
        llm = AsyncMock()
        flusher, _, memory, prefs = _make_flusher(llm=llm)

        result = await flusher.flush(
            user="Guest",
            messages=[_msg("user", "hi"), _msg("assistant", "hi")],
        )

        assert result.is_empty
        llm.complete.assert_not_called()
        memory.store_turn.assert_not_called()
        prefs.reinforce.assert_not_called()

    async def test_empty_user_skipped(self):
        llm = AsyncMock()
        flusher, _, _, _ = _make_flusher(llm=llm)

        result = await flusher.flush(user="", messages=[_msg("user", "hi")])

        assert result.is_empty
        llm.complete.assert_not_called()

    async def test_empty_messages_skipped(self):
        llm = AsyncMock()
        flusher, _, _, _ = _make_flusher(llm=llm)

        result = await flusher.flush(user="jackson", messages=[])

        assert result.is_empty
        llm.complete.assert_not_called()


class TestFlushFailureModes:
    async def test_invalid_json_returns_empty(self):
        llm = AsyncMock()
        llm.complete.return_value = "not json at all"
        flusher, _, memory, prefs = _make_flusher(llm=llm)

        result = await flusher.flush(
            user="jackson", messages=[_msg("user", "x")],
        )

        assert result.is_empty
        memory.store_turn.assert_not_called()
        prefs.reinforce.assert_not_called()

    async def test_partial_json_keeps_what_parses(self):
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({
            "facts_to_remember": ["A fact"],
            "preferences_to_reinforce": "not a list",   # malformed
            "decisions": [
                {"what": "ok", "why": "ok"},
                {"what": "missing why"},                 # malformed
                {"why": "missing what"},                 # malformed
            ],
        })
        flusher, _, _, _ = _make_flusher(llm=llm)

        result = await flusher.flush(
            user="jackson", messages=[_msg("user", "x")],
        )

        assert result.facts_to_remember == ["A fact"]
        assert result.preferences_to_reinforce == []
        assert result.decisions == [FlushDecision(what="ok", why="ok")]

    async def test_strips_markdown_fences(self):
        llm = AsyncMock()
        payload = json.dumps({
            "facts_to_remember": ["Lives in Berlin"],
            "preferences_to_reinforce": [],
            "decisions": [],
        })
        llm.complete.return_value = f"```json\n{payload}\n```"
        flusher, _, _, _ = _make_flusher(llm=llm)

        result = await flusher.flush(
            user="jackson", messages=[_msg("user", "x")],
        )

        assert result.facts_to_remember == ["Lives in Berlin"]

    async def test_timeout_returns_empty(self):
        async def slow_complete(*args, **kwargs):
            await asyncio.sleep(5.0)
            return "{}"

        llm = AsyncMock()
        llm.complete.side_effect = slow_complete
        flusher, _, memory, _ = _make_flusher(
            llm=llm, timeout_seconds=0.05,
        )

        result = await flusher.flush(
            user="jackson", messages=[_msg("user", "x")],
        )

        assert result.is_empty
        memory.store_turn.assert_not_called()

    async def test_llm_exception_returns_empty(self):
        llm = AsyncMock()
        llm.complete.side_effect = RuntimeError("network down")
        flusher, _, memory, _ = _make_flusher(llm=llm)

        result = await flusher.flush(
            user="jackson", messages=[_msg("user", "x")],
        )

        assert result.is_empty
        memory.store_turn.assert_not_called()

    async def test_reinforce_failure_does_not_block_others(self):
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({
            "facts_to_remember": [],
            "preferences_to_reinforce": ["a", "b", "c"],
            "decisions": [],
        })
        prefs = MagicMock()
        # Second call raises; flush should keep going for the third.
        prefs.reinforce = MagicMock(side_effect=[True, RuntimeError("x"), True])
        flusher, _, _, _ = _make_flusher(llm=llm, preferences=prefs)

        await flusher.flush(user="jackson", messages=[_msg("user", "x")])

        assert prefs.reinforce.call_count == 3


class TestFlushResultEmpty:
    def test_default_is_empty(self):
        assert FlushResult().is_empty

    def test_with_data_is_not_empty(self):
        assert not FlushResult(facts_to_remember=["x"]).is_empty
        assert not FlushResult(preferences_to_reinforce=["x"]).is_empty
        assert not FlushResult(
            decisions=[FlushDecision(what="x", why="y")],
        ).is_empty
