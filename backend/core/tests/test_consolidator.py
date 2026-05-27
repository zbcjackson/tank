"""Tests for memory.consolidator — Dream Consolidation pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.config.models import ConsolidationWeights
from tank_backend.memory.consolidator import (
    ConsolidationCandidate,
    Consolidator,
    _age_days_from_preference_line,
    _format_diary_entry,
    _jaccard,
    _parse_rem_response,
    _recency_score,
    _token_set,
)

_NOW = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)


def _clock() -> datetime:
    return _NOW


def _make_consolidator(
    *,
    tmp_path,
    llm: AsyncMock | None = None,
    memory: MagicMock | None = None,
    preferences: MagicMock | None = None,
    weights: ConsolidationWeights | None = None,
    top_k: int = 20,
    min_idle_minutes: int = 30,
    interval_hours: int = 24,
):
    if llm is None:
        llm = AsyncMock()
    if memory is None:
        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])
    if preferences is None:
        preferences = MagicMock()
        preferences.list_for_user = MagicMock(return_value=[])
        preferences.add_if_new = MagicMock(return_value=True)
        preferences.reinforce = MagicMock(return_value=True)
        preferences.remove = MagicMock(return_value=True)
    # Route diary writes into ``tmp_path/users/<user>/<filename>`` so each
    # test gets its own isolated diary file. Always overrides the mock's
    # auto-generated attribute.
    def _user_file_path(user: str, filename: str):
        return tmp_path / "users" / user / filename
    preferences.user_file_path = MagicMock(side_effect=_user_file_path)
    if weights is None:
        weights = ConsolidationWeights()
    return Consolidator(
        llm=llm,
        memory=memory,
        preferences=preferences,
        diary_filename="DREAMS.md",
        weights=weights,
        top_k=top_k,
        min_idle_minutes=min_idle_minutes,
        interval_hours=interval_hours,
        clock=_clock,
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestTokenSet:
    def test_english_words(self):
        s = _token_set("Hello world Hello")
        assert s == frozenset({"hello", "world"})

    def test_chinese_fallback_to_bigrams(self):
        s = _token_set("你好世界")
        # 你好, 好世, 世界 — 3 character bigrams
        assert "你好" in s
        assert "好世" in s
        assert "世界" in s

    def test_single_char_returns_chars(self):
        s = _token_set("a")
        assert "a" in s


class TestJaccard:
    def test_full_overlap(self):
        a = frozenset({"a", "b", "c"})
        assert _jaccard(a, a) == 1.0

    def test_no_overlap(self):
        a = frozenset({"a", "b"})
        b = frozenset({"x", "y"})
        assert _jaccard(a, b) == 0.0

    def test_partial(self):
        a = frozenset({"a", "b", "c"})
        b = frozenset({"b", "c", "d"})
        assert _jaccard(a, b) == pytest.approx(0.5)

    def test_empty(self):
        assert _jaccard(frozenset(), frozenset({"a"})) == 0.0


class TestRecency:
    def test_today_is_one(self):
        assert _recency_score(0) == 1.0

    def test_ninety_days_is_half(self):
        assert _recency_score(90) == pytest.approx(0.5)

    def test_one_year_is_low(self):
        assert _recency_score(365) < 0.1

    def test_negative_clamped(self):
        assert _recency_score(-5) == 1.0


class TestAgeDays:
    def test_extracts_date(self):
        line = "- Allergic to peanuts [explicit, 2026-05-20]"
        age = _age_days_from_preference_line(line, now=_NOW)
        # _NOW is 2026-05-26 12:00, date is 2026-05-20 00:00 → 6.5 days
        assert age == pytest.approx(6.5, abs=0.01)

    def test_no_date_returns_zero(self):
        assert _age_days_from_preference_line("- bare line", now=_NOW) == 0.0

    def test_bad_date_returns_zero(self):
        line = "- foo [inferred, not-a-date]"
        assert _age_days_from_preference_line(line, now=_NOW) == 0.0


# ---------------------------------------------------------------------------
# REM JSON parser
# ---------------------------------------------------------------------------


class TestParseREMResponse:
    def test_parses_all_actions(self):
        payload = json.dumps({
            "verdicts": [
                {"text": "A", "action": "promote", "reason": "durable"},
                {
                    "text": "B",
                    "action": "consolidate",
                    "winner": "B",
                    "losers": ["B-old"],
                    "reason": "dup",
                },
                {"text": "C", "action": "archive", "reason": "stale"},
                {"text": "D", "action": "keep", "reason": "fine"},
            ]
        })
        verdicts = _parse_rem_response(payload)
        assert len(verdicts) == 4
        actions = [v.action for v in verdicts]
        assert actions == ["promote", "consolidate", "archive", "keep"]
        assert verdicts[1].winner == "B"
        assert verdicts[1].losers == ("B-old",)

    def test_invalid_json_returns_empty(self):
        assert _parse_rem_response("not json") == []

    def test_strips_markdown_fences(self):
        payload = json.dumps({"verdicts": [
            {"text": "x", "action": "keep", "reason": "ok"},
        ]})
        wrapped = f"```json\n{payload}\n```"
        assert len(_parse_rem_response(wrapped)) == 1

    def test_skips_invalid_actions(self):
        payload = json.dumps({"verdicts": [
            {"text": "ok", "action": "promote", "reason": ""},
            {"text": "bad", "action": "destroy", "reason": ""},
        ]})
        out = _parse_rem_response(payload)
        assert len(out) == 1
        assert out[0].action == "promote"

    def test_skips_missing_text(self):
        payload = json.dumps({"verdicts": [
            {"action": "promote", "reason": ""},
            {"text": "", "action": "promote", "reason": ""},
        ]})
        assert _parse_rem_response(payload) == []


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def test_short_unique_facts_get_higher_recency(self, tmp_path):
        cons = _make_consolidator(tmp_path=tmp_path)
        # Two candidates: one new, one old.
        candidates = [
            ConsolidationCandidate(
                text="fresh fact about something", source="preference",
                age_days=0,
            ),
            ConsolidationCandidate(
                text="ancient fact about something", source="preference",
                age_days=365,
            ),
        ]
        scored = cons._score_candidates(candidates)
        # Same texts, fresh should score higher
        # (recency contributes 0.15 * 1.0 vs 0.15 * tiny)
        scored_by_text = {c.text: c.score for c in scored}
        assert scored_by_text["fresh fact about something"] > \
               scored_by_text["ancient fact about something"]

    def test_cross_store_duplicate_boosts_frequency(self, tmp_path):
        cons = _make_consolidator(tmp_path=tmp_path)
        candidates = [
            ConsolidationCandidate(
                text="lives in Berlin", source="preference", age_days=0,
            ),
            ConsolidationCandidate(
                text="lives in Berlin", source="memory", age_days=0,
            ),
            ConsolidationCandidate(
                text="lives in Berlin alone", source="memory", age_days=0,
            ),
        ]
        scored = cons._score_candidates(candidates)
        # Cross-store entries should outscore the memory-only variant.
        cross_store = [c for c in scored if c.text == "lives in Berlin"]
        alone_pref = [
            c for c in scored if c.text == "lives in Berlin alone"
        ]
        assert all(c.score > alone_pref[0].score for c in cross_store)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    async def test_runs_all_phases(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(
            return_value=["Lives in Berlin [inferred, 2026-05-25]"],
        )
        prefs.add_if_new = MagicMock(return_value=True)
        prefs.reinforce = MagicMock(return_value=True)
        prefs.remove = MagicMock(return_value=True)

        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=["Owns Tesla Model 3"])

        llm = AsyncMock()
        llm.complete.return_value = json.dumps({"verdicts": [
            {"text": "Lives in Berlin [inferred, 2026-05-25]",
             "action": "promote", "reason": "durable"},
            {"text": "Owns Tesla Model 3",
             "action": "promote", "reason": "durable"},
        ]})

        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
        )
        report = await cons.run("jackson", force=True)

        assert report.candidates_scanned == 2
        assert "Lives in Berlin [inferred, 2026-05-25]" in report.promoted
        assert "Owns Tesla Model 3" in report.promoted
        # Pinning the inferred preference line: remove+add path
        prefs.add_if_new.assert_called()

    async def test_consolidate_action(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(return_value=[
            "Prefers metric units",
            "Uses celsius",
        ])
        prefs.remove = MagicMock(return_value=True)
        prefs.reinforce = MagicMock(return_value=True)
        prefs.add_if_new = MagicMock(return_value=True)

        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])

        llm = AsyncMock()
        llm.complete.return_value = json.dumps({"verdicts": [
            {
                "text": "Uses celsius",
                "action": "consolidate",
                "winner": "Prefers metric units",
                "losers": ["Uses celsius"],
                "reason": "duplicate",
            },
        ]})

        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
        )
        report = await cons.run("jackson", force=True)

        assert report.consolidated == [
            ("Prefers metric units", ["Uses celsius"]),
        ]
        prefs.reinforce.assert_called_once_with(
            "jackson", "Prefers metric units",
        )
        prefs.remove.assert_called_once_with("jackson", "Uses celsius")

    async def test_archive_action(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(return_value=["Old preference"])
        prefs.remove = MagicMock(return_value=True)

        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])

        llm = AsyncMock()
        llm.complete.return_value = json.dumps({"verdicts": [
            {"text": "Old preference", "action": "archive", "reason": "stale"},
        ]})

        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
        )
        report = await cons.run("jackson", force=True)

        assert "Old preference" in report.archived
        prefs.remove.assert_called_once_with("jackson", "Old preference")

    async def test_empty_candidates_short_circuits(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(return_value=[])
        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])
        llm = AsyncMock()
        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
        )

        report = await cons.run("jackson", force=True)

        assert report.candidates_scanned == 0
        llm.complete.assert_not_called()

    async def test_writes_diary_entry(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(return_value=["Lives in Berlin"])
        prefs.add_if_new = MagicMock(return_value=True)
        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({"verdicts": [
            {"text": "Lives in Berlin", "action": "promote", "reason": "ok"},
        ]})
        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
        )

        await cons.run("jackson", force=True)
        diary = (tmp_path / "users" / "jackson" / "DREAMS.md").read_text(
            encoding="utf-8",
        )
        assert "## " in diary  # ISO timestamp header
        assert "Lives in Berlin" in diary
        assert "Promoted" in diary

    async def test_llm_failure_returns_error_report(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(return_value=["fact"])
        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])
        llm = AsyncMock()
        llm.complete.side_effect = RuntimeError("LLM down")

        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
        )
        report = await cons.run("jackson", force=True)
        assert report.error is not None
        assert report.candidates_scanned == 1
        assert report.promoted == []


class TestGates:
    async def test_idle_gate_blocks(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(return_value=["fact"])
        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])
        llm = AsyncMock()
        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
            min_idle_minutes=30,
        )

        # Last activity 5 minutes ago — should block.
        active = _NOW - timedelta(minutes=5)
        report = await cons.run("jackson", last_user_activity=active)
        assert report.error == "not_idle"
        llm.complete.assert_not_called()

    async def test_idle_gate_passes_when_idle(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(return_value=["fact"])
        prefs.add_if_new = MagicMock(return_value=True)
        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({"verdicts": [
            {"text": "fact", "action": "keep", "reason": ""},
        ]})
        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
            min_idle_minutes=30,
        )

        # 45 minutes ago — should pass.
        active = _NOW - timedelta(minutes=45)
        report = await cons.run("jackson", last_user_activity=active)
        assert report.error is None
        llm.complete.assert_called_once()

    async def test_interval_gate_blocks_repeated_runs(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(return_value=["fact"])
        prefs.add_if_new = MagicMock(return_value=True)
        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({"verdicts": [
            {"text": "fact", "action": "keep", "reason": ""},
        ]})
        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
            interval_hours=24,
        )

        # First run — passes
        await cons.run("jackson", force=True)
        # Second run without force — blocked by interval gate
        report = await cons.run("jackson")
        assert report.error == "interval"

    async def test_force_bypasses_both_gates(self, tmp_path):
        prefs = MagicMock()
        prefs.list_for_user = MagicMock(return_value=["fact"])
        prefs.add_if_new = MagicMock(return_value=True)
        memory = MagicMock()
        memory.get_all = AsyncMock(return_value=[])
        llm = AsyncMock()
        llm.complete.return_value = json.dumps({"verdicts": []})
        cons = _make_consolidator(
            tmp_path=tmp_path, llm=llm,
            memory=memory, preferences=prefs,
        )

        active = _NOW - timedelta(minutes=1)  # would block
        report = await cons.run(
            "jackson", force=True, last_user_activity=active,
        )
        assert report.error is None


class TestDiaryFormat:
    def test_empty_report(self):
        from tank_backend.memory.consolidator import ConsolidationReport
        report = ConsolidationReport(
            started_at=_NOW, finished_at=_NOW,
            user="jackson", candidates_scanned=0,
        )
        text = _format_diary_entry(report)
        # Diary is per-user now — header is just the ISO timestamp.
        assert _NOW.isoformat() in text
        assert "no changes" in text

    def test_error_report(self):
        from tank_backend.memory.consolidator import ConsolidationReport
        report = ConsolidationReport(
            started_at=_NOW, finished_at=_NOW,
            user="jackson", candidates_scanned=0,
            error="not_idle",
        )
        text = _format_diary_entry(report)
        assert "skipped: not_idle" in text
