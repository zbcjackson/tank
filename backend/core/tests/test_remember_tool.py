"""Tests for tools.remember — RememberTool (pinned tier deliberate-write)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tank_backend.preferences.store import PreferenceStore
from tank_backend.tools.remember import RememberTool


@pytest.fixture
def store(tmp_path: Path) -> PreferenceStore:
    return PreferenceStore(tmp_path, max_entries=20)


@pytest.fixture
def tool(store: PreferenceStore) -> RememberTool:
    return RememberTool(store)


class TestRememberToolPin:
    @pytest.mark.asyncio
    async def test_pin_adds_pinned_entry(
        self, tool: RememberTool, store: PreferenceStore,
    ):
        result = await tool.execute(
            action="pin", content="Allergic to peanuts", user="Jackson",
        )
        data = json.loads(result.content)
        assert data["pinned"] is True
        assert store.list_pinned("Jackson") == ["Allergic to peanuts"]

    @pytest.mark.asyncio
    async def test_pin_writes_pinned_source_to_disk(
        self, tool: RememberTool, tmp_path: Path,
    ):
        await tool.execute(
            action="pin", content="Allergic to peanuts", user="Jackson",
        )
        prefs_file = tmp_path / "users" / "jackson" / "preferences.md"
        raw = prefs_file.read_text()
        assert "[pinned," in raw

    @pytest.mark.asyncio
    async def test_pin_duplicate_returns_false(self, tool: RememberTool):
        await tool.execute(
            action="pin", content="Allergic to peanuts", user="Jackson",
        )
        result = await tool.execute(
            action="pin", content="Allergic to peanuts", user="Jackson",
        )
        data = json.loads(result.content)
        assert data["pinned"] is False

    @pytest.mark.asyncio
    async def test_pin_without_content_errors(self, tool: RememberTool):
        result = await tool.execute(action="pin", content="", user="Jackson")
        assert result.error is True

    @pytest.mark.asyncio
    async def test_pin_guest_user_errors(self, tool: RememberTool):
        result = await tool.execute(action="pin", content="x", user="Guest")
        assert result.error is True

    @pytest.mark.asyncio
    async def test_pin_unknown_user_errors(self, tool: RememberTool):
        result = await tool.execute(action="pin", content="x", user="Unknown")
        assert result.error is True

    @pytest.mark.asyncio
    async def test_pin_empty_user_errors(self, tool: RememberTool):
        result = await tool.execute(action="pin", content="x", user="")
        assert result.error is True


class TestRememberToolUnpin:
    @pytest.mark.asyncio
    async def test_unpin_removes_existing(
        self, tool: RememberTool, store: PreferenceStore,
    ):
        store.add_if_new("Jackson", "Allergic to peanuts", source="pinned")
        result = await tool.execute(
            action="unpin", content="peanuts", user="Jackson",
        )
        data = json.loads(result.content)
        assert data["unpinned"] is True
        assert store.list_pinned("Jackson") == []

    @pytest.mark.asyncio
    async def test_unpin_nonexistent(self, tool: RememberTool):
        result = await tool.execute(
            action="unpin", content="nope", user="Jackson",
        )
        data = json.loads(result.content)
        assert data["unpinned"] is False

    @pytest.mark.asyncio
    async def test_unpin_without_content_errors(self, tool: RememberTool):
        result = await tool.execute(action="unpin", content="", user="Jackson")
        assert result.error is True


class TestRememberToolList:
    @pytest.mark.asyncio
    async def test_list_empty(self, tool: RememberTool):
        result = await tool.execute(action="list", user="Jackson")
        data = json.loads(result.content)
        assert data["pinned"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_returns_only_pinned(
        self, tool: RememberTool, store: PreferenceStore,
    ):
        store.add_if_new("Jackson", "Pinned A", source="pinned")
        store.add_if_new("Jackson", "Inferred B", source="inferred")
        store.add_if_new("Jackson", "Explicit C", source="explicit")

        result = await tool.execute(action="list", user="Jackson")
        data = json.loads(result.content)
        assert data["count"] == 1
        assert data["pinned"] == ["Pinned A"]


class TestRememberToolErrors:
    @pytest.mark.asyncio
    async def test_unknown_action(self, tool: RememberTool):
        result = await tool.execute(action="invalid", user="Jackson")
        assert result.error is True
        assert "unknown action" in result.display.lower()
