"""Tests for tools.preference_tool — PreferenceTool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tank_backend.preferences.store import PreferenceStore
from tank_backend.tools.preference_tool import PreferenceTool


@pytest.fixture
def store(tmp_path: Path) -> PreferenceStore:
    return PreferenceStore(tmp_path, max_entries=20)


@pytest.fixture
def tool(store: PreferenceStore) -> PreferenceTool:
    return PreferenceTool(store)


class TestPreferenceToolSave:
    @pytest.mark.asyncio
    async def test_save_adds_preference(self, tool: PreferenceTool, store: PreferenceStore):
        result = await tool.execute(action="save", content="Prefers Celsius", user="Jackson")
        data = json.loads(result.content)
        assert data["added"] is True
        assert store.list_for_user("Jackson") == ["Prefers Celsius"]

    @pytest.mark.asyncio
    async def test_save_duplicate_returns_false(self, tool: PreferenceTool):
        await tool.execute(action="save", content="Prefers Celsius", user="Jackson")
        result = await tool.execute(action="save", content="Prefers Celsius", user="Jackson")
        data = json.loads(result.content)
        assert data["added"] is False

    @pytest.mark.asyncio
    async def test_save_without_content_errors(self, tool: PreferenceTool):
        result = await tool.execute(action="save", content="", user="Jackson")
        assert result.error is True

    @pytest.mark.asyncio
    async def test_save_without_user_uses_default(
        self, tool: PreferenceTool, store: PreferenceStore,
    ):
        result = await tool.execute(action="save", content="Some pref", user="")
        data = json.loads(result.content)
        assert data["added"] is True
        assert store.list_for_user("_default") == ["Some pref"]


class TestPreferenceToolRemove:
    @pytest.mark.asyncio
    async def test_remove_existing(self, tool: PreferenceTool, store: PreferenceStore):
        store.add_if_new("Jackson", "Prefers Celsius")
        result = await tool.execute(action="remove", content="Celsius", user="Jackson")
        data = json.loads(result.content)
        assert data["removed"] is True
        assert store.list_for_user("Jackson") == []

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, tool: PreferenceTool):
        result = await tool.execute(action="remove", content="nonexistent", user="Jackson")
        data = json.loads(result.content)
        assert data["removed"] is False

    @pytest.mark.asyncio
    async def test_remove_without_content_errors(self, tool: PreferenceTool):
        result = await tool.execute(action="remove", content="", user="Jackson")
        assert result.error is True


class TestPreferenceToolList:
    @pytest.mark.asyncio
    async def test_list_empty(self, tool: PreferenceTool):
        result = await tool.execute(action="list", user="Jackson")
        data = json.loads(result.content)
        assert data["preferences"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_with_entries(self, tool: PreferenceTool, store: PreferenceStore):
        store.add_if_new("Jackson", "Prefers Celsius")
        store.add_if_new("Jackson", "Likes brief greetings")
        result = await tool.execute(action="list", user="Jackson")
        data = json.loads(result.content)
        assert data["count"] == 2
        assert "Prefers Celsius" in data["preferences"]


class TestPreferenceToolErrors:
    @pytest.mark.asyncio
    async def test_unknown_action(self, tool: PreferenceTool):
        result = await tool.execute(action="invalid", user="Jackson")
        assert result.error is True
        assert "unknown action" in result.display.lower()
