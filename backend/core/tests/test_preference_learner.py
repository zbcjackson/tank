"""Tests for preferences.learner — PreferenceLearner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.preferences.learner import PreferenceLearner, _parse_json_list
from tank_backend.preferences.store import PreferenceStore


@pytest.fixture
def store(tmp_path: Path) -> PreferenceStore:
    return PreferenceStore(tmp_path, max_entries=20)


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value='[]')
    return llm


@pytest.fixture
def learner(store: PreferenceStore, mock_llm: MagicMock) -> PreferenceLearner:
    return PreferenceLearner(store, mock_llm)


# ------------------------------------------------------------------
# _parse_json_list
# ------------------------------------------------------------------


class TestParseJsonList:
    def test_valid_array(self):
        assert _parse_json_list('["Prefers Celsius"]') == ["Prefers Celsius"]

    def test_empty_array(self):
        assert _parse_json_list("[]") == []

    def test_multiple_entries(self):
        result = _parse_json_list('["Prefers Celsius", "Likes brief greetings"]')
        assert result == ["Prefers Celsius", "Likes brief greetings"]

    def test_strips_whitespace(self):
        assert _parse_json_list('  ["  hello  "]  ') == ["hello"]

    def test_filters_non_strings(self):
        assert _parse_json_list('[1, "valid", null, true]') == ["valid"]

    def test_filters_empty_strings(self):
        assert _parse_json_list('["valid", "", "  "]') == ["valid"]

    def test_markdown_fences(self):
        text = '```json\n["Prefers Celsius"]\n```'
        assert _parse_json_list(text) == ["Prefers Celsius"]

    def test_malformed_json(self):
        assert _parse_json_list("not json at all") == []

    def test_json_object_instead_of_array(self):
        assert _parse_json_list('{"key": "value"}') == []

    def test_empty_string(self):
        assert _parse_json_list("") == []


# ------------------------------------------------------------------
# PreferenceLearner.analyze_turn
# ------------------------------------------------------------------


class TestAnalyzeTurnSkips:
    @pytest.mark.asyncio
    async def test_skips_short_text(self, learner: PreferenceLearner, mock_llm: MagicMock):
        await learner.analyze_turn("Jackson", "hi", "Hello!")
        mock_llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_unknown_user(self, learner: PreferenceLearner, mock_llm: MagicMock):
        await learner.analyze_turn("Unknown", "I prefer Celsius for weather", "OK!")
        mock_llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_empty_user(self, learner: PreferenceLearner, mock_llm: MagicMock):
        # Empty user doesn't match "Unknown" but len check still applies
        await learner.analyze_turn("", "short", "response")
        mock_llm.complete.assert_not_called()


class TestAnalyzeTurnExtraction:
    @pytest.mark.asyncio
    async def test_extracts_and_stores(
        self, learner: PreferenceLearner, mock_llm: MagicMock, store: PreferenceStore,
    ):
        mock_llm.complete = AsyncMock(
            return_value='["Prefers weather in Celsius"]',
        )
        await learner.analyze_turn(
            "Jackson",
            "I always want weather in Celsius",
            "Sure, I'll use Celsius from now on.",
        )
        mock_llm.complete.assert_called_once()
        assert store.list_for_user("Jackson") == ["Prefers weather in Celsius"]

    @pytest.mark.asyncio
    async def test_empty_extraction_stores_nothing(
        self, learner: PreferenceLearner, mock_llm: MagicMock, store: PreferenceStore,
    ):
        mock_llm.complete = AsyncMock(return_value="[]")
        await learner.analyze_turn(
            "Jackson",
            "What is the capital of France?",
            "The capital of France is Paris.",
        )
        assert store.list_for_user("Jackson") == []

    @pytest.mark.asyncio
    async def test_multiple_preferences_extracted(
        self, learner: PreferenceLearner, mock_llm: MagicMock, store: PreferenceStore,
    ):
        mock_llm.complete = AsyncMock(
            return_value='["Prefers Celsius", "Likes brief answers"]',
        )
        await learner.analyze_turn(
            "Jackson",
            "Give me weather in Celsius, keep it short",
            "Tokyo: 22°C, sunny.",
        )
        entries = store.list_for_user("Jackson")
        assert len(entries) == 2
        assert "Prefers Celsius" in entries
        assert "Likes brief answers" in entries

    @pytest.mark.asyncio
    async def test_malformed_response_stores_nothing(
        self, learner: PreferenceLearner, mock_llm: MagicMock, store: PreferenceStore,
    ):
        mock_llm.complete = AsyncMock(return_value="I think the user likes Celsius")
        await learner.analyze_turn(
            "Jackson",
            "I always want weather in Celsius",
            "Sure, I'll use Celsius.",
        )
        assert store.list_for_user("Jackson") == []

    @pytest.mark.asyncio
    async def test_source_is_inferred(
        self, learner: PreferenceLearner, mock_llm: MagicMock, store: PreferenceStore,
    ):
        mock_llm.complete = AsyncMock(return_value='["Prefers Celsius"]')
        await learner.analyze_turn(
            "Jackson",
            "I always want weather in Celsius",
            "Sure, I'll use Celsius.",
        )
        # Check the raw file for [inferred, ...] tag
        prefs_file = store._prefs_path("Jackson")
        raw = prefs_file.read_text()
        assert "[inferred," in raw


class TestAnalyzeTurnRetry:
    @pytest.mark.asyncio
    async def test_retries_on_failure(
        self, learner: PreferenceLearner, mock_llm: MagicMock, store: PreferenceStore,
    ):
        mock_llm.complete = AsyncMock(
            side_effect=[
                RuntimeError("API error"),
                '["Prefers Celsius"]',
            ],
        )
        await learner.analyze_turn(
            "Jackson",
            "I always want weather in Celsius",
            "Sure, I'll use Celsius.",
        )
        assert mock_llm.complete.call_count == 2
        assert store.list_for_user("Jackson") == ["Prefers Celsius"]

    @pytest.mark.asyncio
    async def test_gives_up_after_3_failures(
        self, learner: PreferenceLearner, mock_llm: MagicMock, store: PreferenceStore,
    ):
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("API error"))
        await learner.analyze_turn(
            "Jackson",
            "I always want weather in Celsius",
            "Sure, I'll use Celsius.",
        )
        assert mock_llm.complete.call_count == 3
        assert store.list_for_user("Jackson") == []


class TestAnalyzeTurnDedup:
    @pytest.mark.asyncio
    async def test_deduplicates_with_existing(
        self, learner: PreferenceLearner, mock_llm: MagicMock, store: PreferenceStore,
    ):
        store.add_if_new("Jackson", "Prefers Celsius", source="explicit")
        mock_llm.complete = AsyncMock(return_value='["Prefers Celsius"]')
        await learner.analyze_turn(
            "Jackson",
            "I always want weather in Celsius",
            "Sure, I'll use Celsius.",
        )
        # Should still be 1 entry, not 2
        assert len(store.list_for_user("Jackson")) == 1
