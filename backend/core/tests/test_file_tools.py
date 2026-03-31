"""Tests for file tools — FileReadTool, FileWriteTool, FileDeleteTool, FileListTool."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.policy.backup import BackupManager
from tank_backend.policy.file_access import AccessDecision, FileAccessPolicy
from tank_backend.tools.file_delete import FileDeleteTool
from tank_backend.tools.file_list import FileListTool
from tank_backend.tools.file_read import FileReadTool
from tank_backend.tools.file_write import FileWriteTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_policy(level: str = "allow", reason: str = "test") -> FileAccessPolicy:
    """Return a policy that always returns the given level."""
    policy = MagicMock(spec=FileAccessPolicy)
    policy.evaluate.return_value = AccessDecision(level=level, reason=reason)
    return policy


def _make_backup(backup_path: str | None = "/backup/file.txt") -> BackupManager:
    backup = MagicMock(spec=BackupManager)
    backup.snapshot = AsyncMock(return_value=backup_path)
    return backup


def _make_approval(approved: bool = True) -> AsyncMock:
    """Return a mock ApprovalCallback that returns approved/denied."""
    return AsyncMock(return_value=approved)


# ---------------------------------------------------------------------------
# FileReadTool
# ---------------------------------------------------------------------------

class TestFileReadTool:
    def test_get_info(self):
        tool = FileReadTool(_make_policy())
        info = tool.get_info()
        assert info.name == "file_read"
        assert len(info.parameters) >= 1

    @pytest.mark.asyncio
    async def test_read_allowed(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world")

        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path=str(f))

        assert "content" in result
        assert result["content"] == "hello world"
        assert result["size"] == 11

    @pytest.mark.asyncio
    async def test_read_denied(self):
        tool = FileReadTool(_make_policy("deny", "Secrets"))
        result = await tool.execute(path="/fake/.ssh/id_rsa")

        assert result.get("denied") is True
        assert "Secrets" in result["message"]

    @pytest.mark.asyncio
    async def test_read_require_approval_granted(self, tmp_path: Path):
        f = tmp_path / "config.txt"
        f.write_text("config data")
        cb = _make_approval(True)

        tool = FileReadTool(_make_policy("require_approval", "System config"), approval_callback=cb)
        result = await tool.execute(path=str(f))

        assert "content" in result
        assert result["content"] == "config data"
        cb.assert_awaited_once_with("file_read", str(f), "read", "System config")

    @pytest.mark.asyncio
    async def test_read_require_approval_denied(self):
        cb = _make_approval(False)

        tool = FileReadTool(_make_policy("require_approval", "System config"), approval_callback=cb)
        result = await tool.execute(path="/etc/hosts")

        assert result.get("denied") is True
        assert "denied" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_read_require_approval_no_callback_denies(self):
        """When require_approval but no callback is set, default to deny."""
        tool = FileReadTool(_make_policy("require_approval", "System config"))
        result = await tool.execute(path="/etc/hosts")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_read_file_not_found(self):
        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path="/nonexistent/file.txt")

        assert "error" in result
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_read_not_a_file(self, tmp_path: Path):
        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path=str(tmp_path))

        assert "error" in result
        assert "not a file" in result["message"].lower()


# ---------------------------------------------------------------------------
# FileWriteTool
# ---------------------------------------------------------------------------

class TestFileWriteTool:
    def test_get_info(self):
        tool = FileWriteTool(_make_policy(), _make_backup())
        info = tool.get_info()
        assert info.name == "file_write"

    @pytest.mark.asyncio
    async def test_write_allowed(self, tmp_path: Path):
        f = tmp_path / "output.txt"
        backup = _make_backup(None)  # No existing file to back up

        tool = FileWriteTool(_make_policy("allow"), backup)
        result = await tool.execute(path=str(f), content="new content")

        assert f.read_text() == "new content"
        assert result["size"] == len("new content")
        assert "backup_path" not in result

    @pytest.mark.asyncio
    async def test_write_with_backup(self, tmp_path: Path):
        f = tmp_path / "existing.txt"
        f.write_text("old content")
        backup = _make_backup("/backup/existing.txt")

        tool = FileWriteTool(_make_policy("allow"), backup)
        result = await tool.execute(path=str(f), content="new content")

        assert f.read_text() == "new content"
        assert result["backup_path"] == "/backup/existing.txt"
        backup.snapshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_denied(self):
        tool = FileWriteTool(_make_policy("deny", "Secrets"), _make_backup())
        result = await tool.execute(path="/fake/.ssh/id_rsa", content="hack")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_write_require_approval_granted(self, tmp_path: Path):
        f = tmp_path / "config.txt"
        cb = _make_approval(True)
        backup = _make_backup(None)

        tool = FileWriteTool(_make_policy("require_approval", "System"), backup, approval_callback=cb)
        result = await tool.execute(path=str(f), content="new config")

        assert f.read_text() == "new config"
        cb.assert_awaited_once_with("file_write", str(f), "write", "System")

    @pytest.mark.asyncio
    async def test_write_require_approval_denied(self):
        cb = _make_approval(False)

        tool = FileWriteTool(_make_policy("require_approval"), _make_backup(), approval_callback=cb)
        result = await tool.execute(path="/etc/hosts", content="x")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_write_require_approval_no_callback_denies(self):
        tool = FileWriteTool(_make_policy("require_approval"), _make_backup())
        result = await tool.execute(path="/etc/hosts", content="x")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tmp_path: Path):
        f = tmp_path / "sub" / "dir" / "file.txt"

        tool = FileWriteTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(path=str(f), content="nested")

        assert f.read_text() == "nested"


# ---------------------------------------------------------------------------
# FileDeleteTool
# ---------------------------------------------------------------------------

class TestFileDeleteTool:
    def test_get_info(self):
        tool = FileDeleteTool(_make_policy(), _make_backup())
        info = tool.get_info()
        assert info.name == "file_delete"

    @pytest.mark.asyncio
    async def test_delete_allowed(self, tmp_path: Path):
        f = tmp_path / "doomed.txt"
        f.write_text("goodbye")
        backup = _make_backup("/backup/doomed.txt")

        tool = FileDeleteTool(_make_policy("allow"), backup)
        result = await tool.execute(path=str(f))

        assert not f.exists()
        assert result["backup_path"] == "/backup/doomed.txt"

    @pytest.mark.asyncio
    async def test_delete_denied(self):
        tool = FileDeleteTool(_make_policy("deny", "System"), _make_backup())
        result = await tool.execute(path="/etc/passwd")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_delete_require_approval_granted(self, tmp_path: Path):
        f = tmp_path / "temp.txt"
        f.write_text("temp")
        cb = _make_approval(True)
        backup = _make_backup("/backup/temp.txt")

        tool = FileDeleteTool(_make_policy("require_approval", "Caution"), backup, approval_callback=cb)
        result = await tool.execute(path=str(f))

        assert not f.exists()
        cb.assert_awaited_once_with("file_delete", str(f), "delete", "Caution")

    @pytest.mark.asyncio
    async def test_delete_require_approval_denied(self):
        cb = _make_approval(False)

        tool = FileDeleteTool(_make_policy("require_approval"), _make_backup(), approval_callback=cb)
        result = await tool.execute(path="/tmp/file.txt")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_delete_require_approval_no_callback_denies(self):
        tool = FileDeleteTool(_make_policy("require_approval"), _make_backup())
        result = await tool.execute(path="/tmp/file.txt")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self):
        tool = FileDeleteTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(path="/nonexistent/file.txt")

        assert "error" in result
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_not_a_file(self, tmp_path: Path):
        tool = FileDeleteTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(path=str(tmp_path))

        assert "error" in result
        assert "not a file" in result["message"].lower()


# ---------------------------------------------------------------------------
# FileListTool
# ---------------------------------------------------------------------------

class TestFileListTool:
    def test_get_info(self):
        tool = FileListTool(_make_policy())
        info = tool.get_info()
        assert info.name == "file_list"

    @pytest.mark.asyncio
    async def test_list_directory(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("bb")
        (tmp_path / "subdir").mkdir()

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(path=str(tmp_path))

        assert result["count"] == 3
        names = [e["name"] for e in result["entries"]]
        assert "a.txt" in names
        assert "b.txt" in names
        assert "subdir" in names

    @pytest.mark.asyncio
    async def test_list_hides_hidden_by_default(self, tmp_path: Path):
        (tmp_path / "visible.txt").write_text("v")
        (tmp_path / ".hidden").write_text("h")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(path=str(tmp_path))

        names = [e["name"] for e in result["entries"]]
        assert "visible.txt" in names
        assert ".hidden" not in names

    @pytest.mark.asyncio
    async def test_list_shows_hidden_when_requested(self, tmp_path: Path):
        (tmp_path / "visible.txt").write_text("v")
        (tmp_path / ".hidden").write_text("h")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(path=str(tmp_path), show_hidden=True)

        names = [e["name"] for e in result["entries"]]
        assert ".hidden" in names

    @pytest.mark.asyncio
    async def test_list_denied(self):
        tool = FileListTool(_make_policy("deny", "Secrets"))
        result = await tool.execute(path="/fake/.ssh")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_list_require_approval_granted(self, tmp_path: Path):
        (tmp_path / "file.txt").write_text("x")
        cb = _make_approval(True)

        tool = FileListTool(_make_policy("require_approval", "Sensitive"), approval_callback=cb)
        result = await tool.execute(path=str(tmp_path))

        assert result["count"] == 1
        cb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_require_approval_denied(self):
        cb = _make_approval(False)

        tool = FileListTool(_make_policy("require_approval"), approval_callback=cb)
        result = await tool.execute(path="/tmp")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_list_require_approval_no_callback_denies(self):
        tool = FileListTool(_make_policy("require_approval"))
        result = await tool.execute(path="/tmp")

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_list_not_a_directory(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("not a dir")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(path=str(f))

        assert "error" in result
        assert "not a directory" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_list_not_found(self):
        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(path="/nonexistent/dir")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_entry_types(self, tmp_path: Path):
        (tmp_path / "file.txt").write_text("content")
        (tmp_path / "subdir").mkdir()

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(path=str(tmp_path))

        entries = {e["name"]: e for e in result["entries"]}
        assert entries["file.txt"]["type"] == "file"
        assert entries["file.txt"]["size"] == 7
        assert entries["subdir"]["type"] == "dir"
        assert entries["subdir"]["size"] is None
