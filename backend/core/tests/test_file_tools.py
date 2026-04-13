"""Tests for file tools — all six file tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.policy.backup import BackupManager
from tank_backend.policy.file_access import AccessDecision, FileAccessPolicy
from tank_backend.tools.file_delete import FileDeleteTool
from tank_backend.tools.file_edit import FileEditTool
from tank_backend.tools.file_list import FileListTool
from tank_backend.tools.file_read import FileReadTool
from tank_backend.tools.file_search import FileSearchTool
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

        tool = FileWriteTool(
            _make_policy("require_approval", "System"), backup, approval_callback=cb
        )
        await tool.execute(path=str(f), content="new config")

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
        await tool.execute(path=str(f), content="nested")

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

        tool = FileDeleteTool(
            _make_policy("require_approval", "Caution"), backup, approval_callback=cb
        )
        await tool.execute(path=str(f))

        assert not f.exists()
        cb.assert_awaited_once_with("file_delete", str(f), "delete", "Caution")

    @pytest.mark.asyncio
    async def test_delete_require_approval_denied(self):
        cb = _make_approval(False)

        tool = FileDeleteTool(
            _make_policy("require_approval"), _make_backup(), approval_callback=cb
        )
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


class TestFileListGlob:
    """Tests for the glob/find-by-name feature of file_list."""

    @pytest.mark.asyncio
    async def test_glob_finds_directory_by_name(self, tmp_path: Path):
        (tmp_path / "教材").mkdir()
        (tmp_path / "notes").mkdir()
        (tmp_path / "readme.txt").write_text("hi")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), glob="*教材*",
        )

        assert result["count"] == 1
        assert result["entries"][0]["name"] == "教材"
        assert result["entries"][0]["type"] == "dir"

    @pytest.mark.asyncio
    async def test_glob_finds_files_by_extension(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        (tmp_path / "c.py").write_text("x")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), glob="*.py",
        )

        assert result["count"] == 2
        names = {e["name"] for e in result["entries"]}
        assert names == {"a.py", "c.py"}

    @pytest.mark.asyncio
    async def test_glob_recursive(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.py").write_text("x")
        (sub / "nested.py").write_text("x")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), glob="*.py",
        )

        assert result["count"] == 2
        names = {e["name"] for e in result["entries"]}
        assert names == {"top.py", "nested.py"}

    @pytest.mark.asyncio
    async def test_glob_skips_hidden_dirs(self, tmp_path: Path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("x")
        (tmp_path / "visible.py").write_text("x")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), glob="*.py",
        )

        assert result["count"] == 1
        assert result["entries"][0]["name"] == "visible.py"

    @pytest.mark.asyncio
    async def test_glob_max_results(self, tmp_path: Path):
        for i in range(20):
            (tmp_path / f"file_{i}.txt").write_text("x")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), glob="*.txt", max_results=5,
        )

        assert result["count"] == 5
        assert result.get("truncated") is True

    @pytest.mark.asyncio
    async def test_glob_includes_relative_path(self, tmp_path: Path):
        sub = tmp_path / "deep" / "nested"
        sub.mkdir(parents=True)
        (sub / "target.txt").write_text("x")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), glob="target.txt",
        )

        assert result["count"] == 1
        entry = result["entries"][0]
        assert entry["relative_path"] == "deep/nested/target.txt"
        assert entry["path"] == str(sub / "target.txt")

    @pytest.mark.asyncio
    async def test_glob_no_matches(self, tmp_path: Path):
        (tmp_path / "file.txt").write_text("x")

        tool = FileListTool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), glob="*.nonexistent",
        )

        assert result["count"] == 0
        assert result["entries"] == []

    @pytest.mark.asyncio
    async def test_glob_denied(self):
        tool = FileListTool(_make_policy("deny", "Secrets"))
        result = await tool.execute(
            path="/fake/.ssh", glob="*",
        )

        assert result.get("denied") is True


# ---------------------------------------------------------------------------
# FileReadTool — large and binary file handling
# ---------------------------------------------------------------------------

class TestFileReadLargeAndBinary:
    @pytest.mark.asyncio
    async def test_binary_file_rejected(self, tmp_path: Path):
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path=str(f))

        assert "error" in result
        assert result["error"] == "Binary file"
        assert "binary" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_large_file_rejected(self, tmp_path: Path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 2_000_000)  # 2MB

        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path=str(f), max_size=1_000_000)

        assert result["error"] == "File too large"
        assert result["size"] == 2_000_000
        assert result["max_size"] == 1_000_000

    @pytest.mark.asyncio
    async def test_large_file_allowed_with_range(self, tmp_path: Path):
        lines = [f"line {i}\n" for i in range(100_000)]
        f = tmp_path / "big.txt"
        f.write_text("".join(lines))

        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path=str(f), max_size=100, offset=0, limit=5)

        assert "content" in result
        assert result["content"].count("\n") == 5
        assert result["limit"] == 5

    @pytest.mark.asyncio
    async def test_offset_and_limit(self, tmp_path: Path):
        f = tmp_path / "lines.txt"
        f.write_text("line0\nline1\nline2\nline3\nline4\n")

        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path=str(f), offset=2, limit=2)

        assert result["content"] == "line2\nline3\n"
        assert result["offset"] == 2
        assert result["limit"] == 2

    @pytest.mark.asyncio
    async def test_offset_only(self, tmp_path: Path):
        f = tmp_path / "lines.txt"
        f.write_text("line0\nline1\nline2\n")

        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path=str(f), offset=1)

        assert result["content"] == "line1\nline2\n"

    @pytest.mark.asyncio
    async def test_custom_max_size(self, tmp_path: Path):
        f = tmp_path / "small.txt"
        f.write_text("hello")

        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path=str(f), max_size=10)

        assert result["content"] == "hello"

    @pytest.mark.asyncio
    async def test_file_size_in_result(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("12345")

        tool = FileReadTool(_make_policy("allow"))
        result = await tool.execute(path=str(f))

        assert result["file_size"] == 5
        assert result["size"] == 5


# ---------------------------------------------------------------------------
# FileEditTool
# ---------------------------------------------------------------------------

class TestFileEditTool:
    def test_get_info(self):
        tool = FileEditTool(_make_policy(), _make_backup())
        info = tool.get_info()
        assert info.name == "file_edit"
        assert len(info.parameters) >= 3

    @pytest.mark.asyncio
    async def test_edit_allowed(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("def hello():\n    return 'world'\n")
        backup = _make_backup("/backup/code.py")

        tool = FileEditTool(_make_policy("allow"), backup)
        result = await tool.execute(
            path=str(f), old_string="'world'", new_string="'universe'",
        )

        assert f.read_text() == "def hello():\n    return 'universe'\n"
        assert result["replacements"] == 1
        assert result["backup_path"] == "/backup/code.py"

    @pytest.mark.asyncio
    async def test_edit_denied(self):
        tool = FileEditTool(_make_policy("deny", "Secrets"), _make_backup())
        result = await tool.execute(
            path="/fake/.ssh/config", old_string="a", new_string="b",
        )
        assert result.get("denied") is True
        assert "Secrets" in result["message"]

    @pytest.mark.asyncio
    async def test_edit_require_approval_granted(self, tmp_path: Path):
        f = tmp_path / "config.txt"
        f.write_text("old_value")
        cb = _make_approval(True)
        backup = _make_backup(None)

        tool = FileEditTool(
            _make_policy("require_approval", "System"), backup, approval_callback=cb,
        )
        await tool.execute(
            path=str(f), old_string="old_value", new_string="new_value",
        )

        assert f.read_text() == "new_value"
        cb.assert_awaited_once_with("file_edit", str(f), "write", "System")

    @pytest.mark.asyncio
    async def test_edit_require_approval_denied(self):
        cb = _make_approval(False)

        tool = FileEditTool(
            _make_policy("require_approval"), _make_backup(), approval_callback=cb,
        )
        result = await tool.execute(
            path="/etc/hosts", old_string="a", new_string="b",
        )
        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_edit_require_approval_no_callback_denies(self):
        tool = FileEditTool(_make_policy("require_approval"), _make_backup())
        result = await tool.execute(
            path="/etc/hosts", old_string="a", new_string="b",
        )
        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self):
        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path="/nonexistent/file.txt", old_string="a", new_string="b",
        )
        assert "error" in result
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_edit_not_a_file(self, tmp_path: Path):
        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path=str(tmp_path), old_string="a", new_string="b",
        )
        assert "error" in result
        assert "not a file" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_edit_old_string_not_found(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello world")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path=str(f), old_string="nonexistent", new_string="x",
        )
        assert "error" in result
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_edit_ambiguous_match(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("foo bar foo baz")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path=str(f), old_string="foo", new_string="qux",
        )
        assert "error" in result
        assert "ambiguous" in result["message"].lower() or "multiple" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_edit_same_old_new_rejected(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path=str(f), old_string="hello", new_string="hello",
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_edit_replace_all(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("foo bar foo baz foo")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path=str(f), old_string="foo", new_string="qux", replace_all=True,
        )

        assert f.read_text() == "qux bar qux baz qux"
        assert result["replacements"] == 3

    # --- Insert mode tests ---

    @pytest.mark.asyncio
    async def test_insert_after_line_middle(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("line1\nline2\nline3\n")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path=str(f), old_string="", new_string="inserted\n",
            insert_after_line=2,
        )

        assert f.read_text() == "line1\nline2\ninserted\nline3\n"
        assert result["insert_after_line"] == 2

    @pytest.mark.asyncio
    async def test_insert_after_line_zero_prepends(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("existing\n")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        await tool.execute(
            path=str(f), old_string="", new_string="first\n",
            insert_after_line=0,
        )

        assert f.read_text() == "first\nexisting\n"

    @pytest.mark.asyncio
    async def test_insert_after_last_line_appends(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("line1\nline2\n")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        await tool.execute(
            path=str(f), old_string="", new_string="line3\n",
            insert_after_line=2,
        )

        assert f.read_text() == "line1\nline2\nline3\n"

    @pytest.mark.asyncio
    async def test_insert_beyond_last_line_appends(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("line1\n")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        await tool.execute(
            path=str(f), old_string="", new_string="appended\n",
            insert_after_line=999,
        )

        assert f.read_text() == "line1\nappended\n"

    @pytest.mark.asyncio
    async def test_insert_negative_line_rejected(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("content\n")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path=str(f), old_string="", new_string="x",
            insert_after_line=-1,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_insert_empty_new_string_rejected(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("content\n")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path=str(f), old_string="", new_string="",
            insert_after_line=1,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_insert_denied(self):
        tool = FileEditTool(_make_policy("deny", "Secrets"), _make_backup())
        result = await tool.execute(
            path="/fake/.ssh/config", old_string="", new_string="x",
            insert_after_line=1,
        )
        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_insert_with_backup(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("line1\n")
        backup = _make_backup("/backup/file.txt")

        tool = FileEditTool(_make_policy("allow"), backup)
        result = await tool.execute(
            path=str(f), old_string="", new_string="line2\n",
            insert_after_line=1,
        )

        assert result["backup_path"] == "/backup/file.txt"

    @pytest.mark.asyncio
    async def test_empty_old_string_without_insert_line_rejected(
        self, tmp_path: Path,
    ):
        """Empty old_string without insert_after_line is ambiguous."""
        f = tmp_path / "file.txt"
        f.write_text("content\n")

        tool = FileEditTool(_make_policy("allow"), _make_backup(None))
        result = await tool.execute(
            path=str(f), old_string="", new_string="x",
        )

        assert "error" in result


# ---------------------------------------------------------------------------
# FileSearchTool
# ---------------------------------------------------------------------------

def _make_search_tool(policy=None, approval_callback=None):
    """Create a FileSearchTool forced to Python fallback (no rg)."""
    with patch("tank_backend.tools.file_search.find_rg_binary", return_value=None):
        return FileSearchTool(
            policy or _make_policy(),
            approval_callback=approval_callback,
        )


class TestFileSearchTool:
    """Core search tests — use Python fallback for deterministic output.

    Default output_mode is now files_with_matches. Tests that check
    line-level content must pass output_mode="content" explicitly.
    """

    def test_get_info(self):
        tool = _make_search_tool()
        info = tool.get_info()
        assert info.name == "file_search"
        assert len(info.parameters) >= 2

    @pytest.mark.asyncio
    async def test_search_literal_content(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("line1\nfoo bar\nline3\nfoo baz\nline5\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(f), pattern="foo", output_mode="content",
        )

        assert "2:foo bar" in result["message"]
        assert "4:foo baz" in result["message"]

    @pytest.mark.asyncio
    async def test_search_regex(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("apple 123\nbanana 456\ncherry 789\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(f), pattern=r"\d{3}", is_regex=True,
            output_mode="content",
        )

        assert "3 line(s)" in result["message"]

    @pytest.mark.asyncio
    async def test_search_with_context(self, tmp_path: Path):
        """Context lines appear in message output."""
        f = tmp_path / "log.txt"
        f.write_text("a\nb\nTARGET\nd\ne\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(f), pattern="TARGET", context_lines=1,
            output_mode="content",
        )

        assert "TARGET" in result["message"]

    @pytest.mark.asyncio
    async def test_search_max_results(self, tmp_path: Path):
        f = tmp_path / "many.txt"
        f.write_text("\n".join(f"match line {i}" for i in range(100)))

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(f), pattern="match", max_results=5,
            output_mode="content",
        )

        assert "5 line(s)" in result["message"]
        assert result.get("truncated") is True

    @pytest.mark.asyncio
    async def test_search_no_matches(self, tmp_path: Path):
        f = tmp_path / "empty_search.txt"
        f.write_text("hello world\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(path=str(f), pattern="nonexistent")

        assert "0 file(s)" in result["message"]

    @pytest.mark.asyncio
    async def test_search_denied(self):
        tool = _make_search_tool(_make_policy("deny", "Secrets"))
        result = await tool.execute(
            path="/fake/.ssh/id_rsa", pattern="key",
        )

        assert result.get("denied") is True
        assert "Secrets" in result["message"]

    @pytest.mark.asyncio
    async def test_search_require_approval_granted(self, tmp_path: Path):
        f = tmp_path / "config.txt"
        f.write_text("password=secret\n")
        cb = _make_approval(True)

        tool = _make_search_tool(
            _make_policy("require_approval", "Sensitive"),
            approval_callback=cb,
        )
        result = await tool.execute(path=str(f), pattern="password")

        assert "1 file(s)" in result["message"]
        cb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_require_approval_denied(self):
        cb = _make_approval(False)

        tool = _make_search_tool(
            _make_policy("require_approval"), approval_callback=cb,
        )
        result = await tool.execute(
            path="/etc/hosts", pattern="localhost",
        )

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_search_require_approval_no_callback_denies(self):
        tool = _make_search_tool(_make_policy("require_approval"))
        result = await tool.execute(
            path="/etc/hosts", pattern="localhost",
        )

        assert result.get("denied") is True

    @pytest.mark.asyncio
    async def test_search_file_not_found(self):
        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path="/nonexistent/file.txt", pattern="x",
        )

        assert "error" in result
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_search_directory_is_valid(self, tmp_path: Path):
        """Directories are valid targets — file_search scans contents."""
        (tmp_path / "a.txt").write_text("nothing here")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), pattern="nonexistent",
        )

        assert "0 file(s)" in result["message"]
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_search_invalid_regex(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(f), pattern="[invalid", is_regex=True,
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_directory_content(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("foo bar\nbaz\n")
        (tmp_path / "b.txt").write_text("no match\n")
        (tmp_path / "c.txt").write_text("foo again\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), pattern="foo",
            output_mode="content",
        )

        assert "foo bar" in result["message"]
        assert "foo again" in result["message"]


class TestFileSearchNewParams:
    """Tests for new parameters added in the ripgrep refactor."""

    @pytest.mark.asyncio
    async def test_search_recursive(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.txt").write_text("target\n")
        (sub / "nested.txt").write_text("target\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), pattern="target",
        )

        assert "2 file(s)" in result["message"]
        assert "top.txt" in result["message"]
        assert "nested.txt" in result["message"]

    @pytest.mark.asyncio
    async def test_search_glob_filter(self, tmp_path: Path):
        (tmp_path / "code.py").write_text("target\n")
        (tmp_path / "data.txt").write_text("target\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), pattern="target", glob="*.py",
        )

        assert "1 file(s)" in result["message"]
        assert "code.py" in result["message"]

    @pytest.mark.asyncio
    async def test_search_file_type_filter(self, tmp_path: Path):
        (tmp_path / "app.py").write_text("target\n")
        (tmp_path / "readme.md").write_text("target\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), pattern="target", file_type="py",
        )

        assert "1 file(s)" in result["message"]
        assert "app.py" in result["message"]

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("Hello\nhello\nHELLO\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(f), pattern="hello", case_insensitive=True,
            output_mode="content",
        )

        assert "3 line(s)" in result["message"]

    @pytest.mark.asyncio
    async def test_search_output_mode_files(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("match\n")
        (tmp_path / "b.txt").write_text("no\n")
        (tmp_path / "c.txt").write_text("match\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), pattern="match",
            output_mode="files_with_matches",
        )

        assert "2 file(s)" in result["message"]
        assert "a.txt" in result["message"]
        assert "c.txt" in result["message"]

    @pytest.mark.asyncio
    async def test_search_output_mode_count(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("foo\nfoo\nbar\n")
        (tmp_path / "b.txt").write_text("foo\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), pattern="foo",
            output_mode="count",
        )

        assert result["num_matches"] == 3
        assert result["num_files"] == 2

    @pytest.mark.asyncio
    async def test_search_head_limit_and_offset(self, tmp_path: Path):
        f = tmp_path / "lines.txt"
        f.write_text(
            "\n".join(f"match {i}" for i in range(20)) + "\n",
        )

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(f), pattern="match",
            head_limit=5, offset=3, output_mode="content",
        )

        assert "5 line(s)" in result["message"]
        assert "4:match 3" in result["message"]

    @pytest.mark.asyncio
    async def test_search_invalid_output_mode(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(f), pattern="hello", output_mode="bad",
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_skips_hidden_dirs(self, tmp_path: Path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.txt").write_text("target\n")
        (tmp_path / "visible.txt").write_text("target\n")

        tool = _make_search_tool(_make_policy("allow"))
        result = await tool.execute(
            path=str(tmp_path), pattern="target",
        )

        assert "1 file(s)" in result["message"]
        assert "visible.txt" in result["message"]


class TestFileSearchRipgrepPath:
    """Tests that verify ripgrep integration via mocked subprocess."""

    @pytest.mark.asyncio
    async def test_uses_ripgrep_when_available(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello world\n")

        with patch(
            "tank_backend.tools.file_search.find_rg_binary",
            return_value="/usr/bin/rg",
        ):
            tool = FileSearchTool(_make_policy("allow"))

        rg_output = str(f)
        mock_result = MagicMock()
        mock_result.lines = [rg_output]
        mock_result.truncated = False
        mock_result.exit_code = 0
        mock_result.error = None

        with patch(
            "tank_backend.tools.file_search.run_ripgrep",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_rg:
            result = await tool.execute(
                path=str(f), pattern="hello",
            )

            mock_rg.assert_awaited_once()
            assert "1 file(s)" in result["message"]

    @pytest.mark.asyncio
    async def test_falls_back_when_rg_missing(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello world\n")

        tool = _make_search_tool(_make_policy("allow"))
        assert tool._rg_binary is None

        result = await tool.execute(path=str(f), pattern="hello")

        assert "1 file(s)" in result["message"]

    @pytest.mark.asyncio
    async def test_ripgrep_error_returned(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello\n")

        with patch(
            "tank_backend.tools.file_search.find_rg_binary",
            return_value="/usr/bin/rg",
        ):
            tool = FileSearchTool(_make_policy("allow"))

        mock_result = MagicMock()
        mock_result.error = "ripgrep error: bad regex"
        mock_result.lines = []
        mock_result.truncated = False
        mock_result.exit_code = 2

        with patch(
            "tank_backend.tools.file_search.run_ripgrep",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await tool.execute(
                path=str(f), pattern="[bad", is_regex=True,
            )

            assert "error" in result
