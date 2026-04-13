"""Tests for ripgrep subprocess runner."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tank_backend.tools.ripgrep import (
    RipgrepResult,
    build_rg_args,
    build_rg_files_args,
    find_rg_binary,
    run_rg_files,
    run_rg_sync,
    run_ripgrep,
)

# ---------------------------------------------------------------------------
# find_rg_binary
# ---------------------------------------------------------------------------

class TestFindRgBinary:
    def test_found_on_path(self):
        with patch("tank_backend.tools.ripgrep.shutil.which", return_value="/usr/bin/rg"):
            assert find_rg_binary() == "/usr/bin/rg"

    def test_not_on_path_found_at_homebrew(self):
        def _is_homebrew(p: str) -> bool:
            return p == "/opt/homebrew/bin/rg"

        with (
            patch("tank_backend.tools.ripgrep.shutil.which", return_value=None),
            patch("tank_backend.tools.ripgrep.os.path.isfile", side_effect=_is_homebrew),
            patch("tank_backend.tools.ripgrep.os.access", return_value=True),
        ):
            assert find_rg_binary() == "/opt/homebrew/bin/rg"

    def test_not_found(self):
        with (
            patch("tank_backend.tools.ripgrep.shutil.which", return_value=None),
            patch("tank_backend.tools.ripgrep.os.path.isfile", return_value=False),
        ):
            assert find_rg_binary() is None


# ---------------------------------------------------------------------------
# build_rg_args
# ---------------------------------------------------------------------------

class TestBuildRgArgs:
    def test_content_mode_defaults(self):
        args = build_rg_args("hello")
        assert "--no-heading" in args
        assert "--with-filename" in args
        assert "--color=never" in args
        assert "--hidden" in args
        assert "--line-number" in args
        assert "-e" in args
        assert args[args.index("-e") + 1] == "hello"
        # No files-with-matches or count
        assert "--files-with-matches" not in args
        assert "--count" not in args

    def test_files_with_matches_mode(self):
        args = build_rg_args("pat", output_mode="files_with_matches")
        assert "--files-with-matches" in args
        assert "--line-number" not in args

    def test_count_mode(self):
        args = build_rg_args("pat", output_mode="count")
        assert "--count" in args
        assert "--line-number" not in args

    def test_glob_filter(self):
        args = build_rg_args("pat", glob="*.py")
        idx = args.index("*.py")
        assert args[idx - 1] == "--glob"

    def test_file_type(self):
        args = build_rg_args("pat", file_type="py")
        idx = args.index("py")
        assert args[idx - 1] == "--type"

    def test_case_insensitive(self):
        args = build_rg_args("pat", case_insensitive=True)
        assert "-i" in args

    def test_multiline(self):
        args = build_rg_args("pat", multiline=True)
        assert "--multiline" in args
        assert "--multiline-dotall" in args

    def test_context_symmetric(self):
        args = build_rg_args("pat", context=3)
        idx = args.index("3")
        assert args[idx - 1] == "-C"

    def test_context_asymmetric(self):
        args = build_rg_args("pat", context_before=2, context_after=5)
        assert "-B" in args
        assert args[args.index("-B") + 1] == "2"
        assert "-A" in args
        assert args[args.index("-A") + 1] == "5"

    def test_fixed_strings(self):
        args = build_rg_args("foo.bar", fixed_strings=True)
        assert "--fixed-strings" in args

    def test_vcs_excludes_present(self):
        args = build_rg_args("pat")
        assert "!.git" in args
        assert "!.svn" in args

    def test_no_line_numbers_when_disabled(self):
        args = build_rg_args("pat", line_numbers=False)
        assert "--line-number" not in args

    def test_context_ignored_for_files_mode(self):
        args = build_rg_args(
            "pat", output_mode="files_with_matches", context=5,
        )
        assert "-C" not in args


# ---------------------------------------------------------------------------
# run_rg_sync
# ---------------------------------------------------------------------------

class TestRunRgSync:
    def _mock_proc(
        self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0,
    ) -> MagicMock:
        proc = MagicMock()
        proc.stdout = stdout
        proc.stderr = stderr
        proc.returncode = returncode
        return proc

    def test_success_with_matches(self):
        proc = self._mock_proc(
            stdout=b"file.py:1:hello world\nfile.py:5:hello again\n",
            returncode=0,
        )
        with patch("tank_backend.tools.ripgrep.subprocess.run", return_value=proc):
            result = run_rg_sync("/usr/bin/rg", ["-e", "hello"], "/tmp")

        assert result.exit_code == 0
        assert result.error is None
        assert len(result.lines) == 2
        assert "hello world" in result.lines[0]

    def test_no_matches(self):
        proc = self._mock_proc(returncode=1)
        with patch("tank_backend.tools.ripgrep.subprocess.run", return_value=proc):
            result = run_rg_sync("/usr/bin/rg", ["-e", "nope"], "/tmp")

        assert result.exit_code == 1
        assert result.error is None
        assert result.lines == []

    def test_rg_error(self):
        proc = self._mock_proc(
            stderr=b"regex parse error", returncode=2,
        )
        with patch("tank_backend.tools.ripgrep.subprocess.run", return_value=proc):
            result = run_rg_sync("/usr/bin/rg", ["-e", "[bad"], "/tmp")

        assert result.exit_code == 2
        assert result.error is not None
        assert "regex parse error" in result.error

    def test_timeout_returns_partial(self):
        exc = subprocess.TimeoutExpired(cmd=["rg"], timeout=20)
        exc.stdout = b"partial:1:line\ncomplete:2:line\nincomplete"
        with patch(
            "tank_backend.tools.ripgrep.subprocess.run", side_effect=exc,
        ):
            result = run_rg_sync("/usr/bin/rg", ["-e", "x"], "/tmp")

        assert result.truncated is True
        assert result.exit_code == -1
        assert "timed out" in result.error
        # Last incomplete line should be dropped
        assert len(result.lines) == 2

    def test_timeout_no_output(self):
        exc = subprocess.TimeoutExpired(cmd=["rg"], timeout=20)
        exc.stdout = None
        with patch(
            "tank_backend.tools.ripgrep.subprocess.run", side_effect=exc,
        ):
            result = run_rg_sync("/usr/bin/rg", ["-e", "x"], "/tmp")

        assert result.truncated is True
        assert result.lines == []

    def test_binary_not_found(self):
        with patch(
            "tank_backend.tools.ripgrep.subprocess.run",
            side_effect=FileNotFoundError("No such file"),
        ):
            result = run_rg_sync("/bad/path/rg", ["-e", "x"], "/tmp")

        assert result.exit_code == -1
        assert "not found" in result.error

    def test_eagain_retries_with_single_thread(self):
        eagain_proc = self._mock_proc(
            stderr=b"os error 11: Resource temporarily unavailable",
            returncode=2,
        )
        success_proc = self._mock_proc(
            stdout=b"file.py:1:found\n", returncode=0,
        )
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return eagain_proc
            return success_proc

        with patch(
            "tank_backend.tools.ripgrep.subprocess.run",
            side_effect=side_effect,
        ):
            result = run_rg_sync(
                "/usr/bin/rg", ["-e", "found"], "/tmp",
            )

        assert call_count == 2
        assert result.exit_code == 0
        assert len(result.lines) == 1

    def test_eagain_no_infinite_retry(self):
        """EAGAIN retry only happens once."""
        eagain_proc = self._mock_proc(
            stderr=b"os error 11: Resource temporarily unavailable",
            returncode=2,
        )
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return eagain_proc

        with patch(
            "tank_backend.tools.ripgrep.subprocess.run",
            side_effect=side_effect,
        ):
            result = run_rg_sync(
                "/usr/bin/rg", ["-e", "x"], "/tmp",
            )

        # First call + one retry = 2
        assert call_count == 2
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# run_ripgrep (async with pagination)
# ---------------------------------------------------------------------------

class TestRunRipgrep:
    @pytest.mark.asyncio
    async def test_pagination_head_limit(self):
        lines = [f"file.py:{i}:line {i}" for i in range(1, 301)]
        mock_result = RipgrepResult(lines=lines, exit_code=0)

        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_ripgrep(
                "/usr/bin/rg", "pattern", "/tmp", head_limit=10,
            )

        assert len(result.lines) == 10
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_pagination_offset(self):
        lines = [f"file.py:{i}:line {i}" for i in range(1, 11)]
        mock_result = RipgrepResult(lines=lines, exit_code=0)

        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_ripgrep(
                "/usr/bin/rg", "pattern", "/tmp",
                offset=5, head_limit=100,
            )

        assert len(result.lines) == 5
        assert "line 6" in result.lines[0]

    @pytest.mark.asyncio
    async def test_pagination_offset_and_limit(self):
        lines = [f"file.py:{i}:line {i}" for i in range(1, 21)]
        mock_result = RipgrepResult(lines=lines, exit_code=0)

        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_ripgrep(
                "/usr/bin/rg", "pattern", "/tmp",
                offset=5, head_limit=3,
            )

        assert len(result.lines) == 3
        assert result.truncated is True
        assert "line 6" in result.lines[0]

    @pytest.mark.asyncio
    async def test_error_passthrough(self):
        mock_result = RipgrepResult(
            exit_code=-1, error="binary not found",
        )
        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_ripgrep(
                "/bad/rg", "pattern", "/tmp",
            )

        assert result.error == "binary not found"

    @pytest.mark.asyncio
    async def test_no_truncation_within_limit(self):
        lines = ["file.py:1:only match"]
        mock_result = RipgrepResult(lines=lines, exit_code=0)

        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_ripgrep(
                "/usr/bin/rg", "pattern", "/tmp", head_limit=250,
            )

        assert len(result.lines) == 1
        assert result.truncated is False

    @pytest.mark.asyncio
    async def test_unlimited_head_limit(self):
        """head_limit=0 means no limit."""
        lines = [f"file.py:{i}:line" for i in range(500)]
        mock_result = RipgrepResult(lines=lines, exit_code=0)

        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_ripgrep(
                "/usr/bin/rg", "pattern", "/tmp", head_limit=0,
            )

        assert len(result.lines) == 500
        assert result.truncated is False


# ---------------------------------------------------------------------------
# build_rg_files_args
# ---------------------------------------------------------------------------

class TestBuildRgFilesArgs:
    def test_defaults(self):
        args = build_rg_files_args()
        assert "--files" in args
        assert "--color=never" in args
        assert "--sort=modified" in args
        # hidden not included by default
        assert "--hidden" not in args

    def test_show_hidden(self):
        args = build_rg_files_args(show_hidden=True)
        assert "--hidden" in args

    def test_glob_filter(self):
        args = build_rg_files_args(glob="*.py")
        idx = args.index("*.py")
        assert args[idx - 1] == "--glob"

    def test_no_sort(self):
        args = build_rg_files_args(sort_modified=False)
        assert "--sort=modified" not in args

    def test_vcs_excludes(self):
        args = build_rg_files_args()
        assert "!.git" in args


# ---------------------------------------------------------------------------
# run_rg_files (async)
# ---------------------------------------------------------------------------

class TestRunRgFiles:
    @pytest.mark.asyncio
    async def test_lists_files(self):
        lines = ["/tmp/a.py", "/tmp/b.py", "/tmp/sub/c.py"]
        mock_result = RipgrepResult(lines=lines, exit_code=0)

        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_rg_files(
                "/usr/bin/rg", "/tmp", glob="*.py",
            )

        assert len(result.lines) == 3
        assert result.truncated is False

    @pytest.mark.asyncio
    async def test_pagination(self):
        lines = [f"/tmp/file_{i}.txt" for i in range(20)]
        mock_result = RipgrepResult(lines=lines, exit_code=0)

        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_rg_files(
                "/usr/bin/rg", "/tmp", head_limit=5, offset=3,
            )

        assert len(result.lines) == 5
        assert result.truncated is True
        assert "file_3" in result.lines[0]

    @pytest.mark.asyncio
    async def test_error_passthrough(self):
        mock_result = RipgrepResult(
            exit_code=-1, error="binary not found",
        )
        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_rg_files("/bad/rg", "/tmp")

        assert result.error == "binary not found"

    @pytest.mark.asyncio
    async def test_filters_macos_bundles(self):
        """Files inside .pages/.app/.numbers bundles are excluded."""
        lines = [
            "/docs/report.pdf",
            "/docs/slides.pages/Data/image.jpg",
            "/docs/slides.pages/Index.zip",
            "/apps/MyApp.app/Contents/Info.plist",
            "/docs/budget.numbers/Data/sheet.xml",
            "/docs/real_file.txt",
        ]
        mock_result = RipgrepResult(lines=lines, exit_code=0)

        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_rg_files(
                "/usr/bin/rg", "/docs", head_limit=0,
            )

        assert len(result.lines) == 2
        assert "/docs/report.pdf" in result.lines
        assert "/docs/real_file.txt" in result.lines

    @pytest.mark.asyncio
    async def test_bundle_filter_keeps_bundle_itself(self):
        """A file named foo.pages (not inside a bundle) is kept."""
        lines = [
            "/docs/foo.pages",
            "/docs/bar.pages/Data/internal.jpg",
        ]
        mock_result = RipgrepResult(lines=lines, exit_code=0)

        with patch(
            "tank_backend.tools.ripgrep.run_rg_sync",
            return_value=mock_result,
        ):
            result = await run_rg_files(
                "/usr/bin/rg", "/docs", head_limit=0,
            )

        # foo.pages itself is kept (it's the filename, not a parent dir)
        # bar.pages/Data/internal.jpg is filtered (inside a bundle)
        assert len(result.lines) == 1
        assert "/docs/foo.pages" in result.lines
