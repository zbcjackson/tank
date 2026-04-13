"""file_search tool — search file/directory contents with policy check.

Uses ripgrep (``rg``) when available for 10-100x faster search with
recursive traversal, ``.gitignore`` respect, and SIMD-accelerated regex.
Falls back to a pure-Python implementation when ``rg`` is not installed.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import re
from pathlib import Path
from typing import Any

from ..policy.file_access import FileAccessPolicy
from .base import ApprovalCallback, BaseTool, ToolInfo, ToolParameter
from .ripgrep import DEFAULT_HEAD_LIMIT, find_rg_binary, run_ripgrep

logger = logging.getLogger(__name__)

# Skip binary files during Python fallback search
_BINARY_SAMPLE_SIZE = 512

# Extension map for file_type filtering in Python fallback
_TYPE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "py": (".py", ".pyi"),
    "js": (".js", ".mjs", ".cjs"),
    "ts": (".ts", ".tsx", ".mts", ".cts"),
    "java": (".java",),
    "go": (".go",),
    "rs": (".rs",),
    "c": (".c", ".h"),
    "cpp": (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"),
    "rb": (".rb",),
    "php": (".php",),
    "swift": (".swift",),
    "kt": (".kt", ".kts"),
    "sh": (".sh", ".bash", ".zsh"),
    "yaml": (".yaml", ".yml"),
    "json": (".json",),
    "toml": (".toml",),
    "xml": (".xml",),
    "html": (".html", ".htm"),
    "css": (".css",),
    "md": (".md", ".markdown"),
    "sql": (".sql",),
}


class FileSearchTool(BaseTool):
    """Search for a pattern in a file or directory, subject to file access policy.

    Uses ripgrep when available, falls back to Python regex scanning.
    """

    def __init__(
        self,
        policy: FileAccessPolicy,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self._policy = policy
        self._approval_callback = approval_callback
        self._rg_binary = find_rg_binary()
        if self._rg_binary:
            logger.info("file_search: using ripgrep at %s", self._rg_binary)
        else:
            logger.info(
                "file_search: ripgrep not found, using Python fallback",
            )

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="file_search",
            description=(
                "Search for a pattern in a file or recursively in a "
                "directory. Supports regex patterns, file type and glob "
                "filtering, multiple output modes, and pagination. "
                "Uses ripgrep when available for fast search."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description=(
                        "Absolute or ~-prefixed path to a file or "
                        "directory to search"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="pattern",
                    type="string",
                    description="The search pattern (regex or literal)",
                    required=True,
                ),
                ToolParameter(
                    name="is_regex",
                    type="boolean",
                    description=(
                        "Treat pattern as regex (default: false). "
                        "When false, pattern is treated as a literal string."
                    ),
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="output_mode",
                    type="string",
                    description=(
                        "Output mode: "
                        "'files_with_matches' (file paths only, default), "
                        "'content' (matching lines with line numbers), "
                        "or 'count' (match counts per file)"
                    ),
                    required=False,
                    default="files_with_matches",
                ),
                ToolParameter(
                    name="glob",
                    type="string",
                    description=(
                        "Glob pattern to filter files "
                        "(e.g. '*.py', '*.{ts,tsx}')"
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="file_type",
                    type="string",
                    description=(
                        "File type to search "
                        "(e.g. 'py', 'js', 'ts', 'go', 'rs')"
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="case_insensitive",
                    type="boolean",
                    description="Case-insensitive search (default: false)",
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="multiline",
                    type="boolean",
                    description=(
                        "Enable multiline matching where . matches "
                        "newlines (default: false)"
                    ),
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="context_lines",
                    type="integer",
                    description=(
                        "Lines of context before and after each match "
                        "(default: 0)"
                    ),
                    required=False,
                    default=0,
                ),
                ToolParameter(
                    name="context_before",
                    type="integer",
                    description="Lines of context before each match",
                    required=False,
                    default=0,
                ),
                ToolParameter(
                    name="context_after",
                    type="integer",
                    description="Lines of context after each match",
                    required=False,
                    default=0,
                ),
                ToolParameter(
                    name="head_limit",
                    type="integer",
                    description=(
                        "Max results to return "
                        f"(default: {DEFAULT_HEAD_LIMIT}). "
                        "Pass 0 for unlimited."
                    ),
                    required=False,
                    default=DEFAULT_HEAD_LIMIT,
                ),
                ToolParameter(
                    name="offset",
                    type="integer",
                    description=(
                        "Skip first N results for pagination "
                        "(default: 0)"
                    ),
                    required=False,
                    default=0,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        path: str = kwargs["path"]
        pattern: str = kwargs["pattern"]
        is_regex: bool = kwargs.get("is_regex", False)
        output_mode: str = kwargs.get("output_mode", "files_with_matches")
        glob_pat: str | None = kwargs.get("glob")
        file_type: str | None = kwargs.get("file_type")
        case_insensitive: bool = kwargs.get("case_insensitive", False)
        multiline: bool = kwargs.get("multiline", False)
        context_lines: int = kwargs.get("context_lines", 0) or 0
        context_before: int = kwargs.get("context_before", 0) or 0
        context_after: int = kwargs.get("context_after", 0) or 0
        head_limit: int = kwargs.get(
            "head_limit",
            kwargs.get("max_results", DEFAULT_HEAD_LIMIT),
        ) or DEFAULT_HEAD_LIMIT
        offset: int = kwargs.get("offset", 0) or 0

        # Validate output_mode
        if output_mode not in ("content", "files_with_matches", "count"):
            return {
                "error": "Invalid output_mode",
                "message": (
                    f"output_mode must be 'content', "
                    f"'files_with_matches', or 'count', "
                    f"got '{output_mode}'"
                ),
            }

        # 1. Policy check (searching is a read operation)
        decision = self._policy.evaluate(path, "read")
        if decision.level == "deny":
            logger.warning(
                "file_search denied: %s (%s)", path, decision.reason,
            )
            return {
                "error": f"Access denied: {path} ({decision.reason})",
                "denied": True,
                "message": f"Cannot search {path}: {decision.reason}",
            }
        if (
            decision.level == "require_approval"
            and not await self._request_approval(
                path, "read", decision.reason,
            )
        ):
            return {
                "error": f"Approval denied: {path} ({decision.reason})",
                "denied": True,
                "message": (
                    f"User denied searching {path}: {decision.reason}"
                ),
            }

        # 2. Resolve path
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return {
                "error": "Not found",
                "message": f"File not found: {path}",
            }

        # 3. Dispatch to ripgrep or Python fallback
        try:
            if self._rg_binary:
                return await self._search_ripgrep(
                    resolved=resolved,
                    pattern=pattern,
                    is_regex=is_regex,
                    output_mode=output_mode,
                    glob_pat=glob_pat,
                    file_type=file_type,
                    case_insensitive=case_insensitive,
                    multiline=multiline,
                    context_lines=context_lines,
                    context_before=context_before,
                    context_after=context_after,
                    head_limit=head_limit,
                    offset=offset,
                )
            return await self._search_python(
                resolved=resolved,
                pattern=pattern,
                is_regex=is_regex,
                output_mode=output_mode,
                glob_pat=glob_pat,
                file_type=file_type,
                case_insensitive=case_insensitive,
                context_lines=context_lines,
                context_before=context_before,
                context_after=context_after,
                head_limit=head_limit,
                offset=offset,
            )
        except Exception as e:
            logger.error("file_search failed: %s", e, exc_info=True)
            return {
                "error": str(e),
                "message": f"Error searching {path}: {e}",
            }

    # ------------------------------------------------------------------
    # Ripgrep path
    # ------------------------------------------------------------------

    async def _search_ripgrep(
        self,
        resolved: Path,
        pattern: str,
        is_regex: bool,
        output_mode: str,
        glob_pat: str | None,
        file_type: str | None,
        case_insensitive: bool,
        multiline: bool,
        context_lines: int,
        context_before: int,
        context_after: int,
        head_limit: int,
        offset: int,
    ) -> dict[str, Any]:
        rg_result = await run_ripgrep(
            self._rg_binary,
            pattern,
            str(resolved),
            output_mode=output_mode,
            glob=glob_pat,
            file_type=file_type,
            case_insensitive=case_insensitive,
            multiline=multiline,
            context_before=context_before,
            context_after=context_after,
            context=context_lines,
            line_numbers=True,
            fixed_strings=not is_regex,
            head_limit=head_limit,
            offset=offset,
        )

        if rg_result.error:
            return {
                "error": rg_result.error,
                "message": rg_result.error,
            }

        return self._format_rg_result(
            rg_result.lines,
            str(resolved),
            pattern,
            output_mode,
            rg_result.truncated,
        )

    @staticmethod
    def _format_rg_result(
        lines: list[str],
        path: str,
        pattern: str,
        output_mode: str,
        truncated: bool,
    ) -> dict[str, Any]:
        """Format ripgrep output lines into the tool result dict.

        Uses relative paths and compact formats to minimize token usage.
        """
        base = Path(path)

        def _rel(abs_path: str) -> str:
            """Convert absolute path to relative if under search root."""
            try:
                return str(Path(abs_path).relative_to(base))
            except ValueError:
                return abs_path

        if output_mode == "files_with_matches":
            files = [_rel(ln.strip()) for ln in lines if ln.strip()]
            content = "\n".join(files) if files else "No files found"
            header = f"Found matches in {len(files)} file(s)"
            if truncated:
                header += " (truncated)"
            result: dict[str, Any] = {
                "path": path,
                "pattern": pattern,
                "num_files": len(files),
                "message": f"{header}\n{content}",
            }
            if truncated:
                result["truncated"] = True
            return result

        if output_mode == "count":
            total = 0
            count_lines: list[str] = []
            for ln in lines:
                if ":" in ln:
                    file_part, _, count_str = ln.rpartition(":")
                    try:
                        c = int(count_str.strip())
                        count_lines.append(f"{_rel(file_part)}:{c}")
                        total += c
                    except ValueError:
                        pass
            content = "\n".join(count_lines) if count_lines else "No matches"
            header = (
                f"Found {total} match(es) across "
                f"{len(count_lines)} file(s)"
            )
            if truncated:
                header += " (truncated)"
            result = {
                "path": path,
                "pattern": pattern,
                "num_files": len(count_lines),
                "num_matches": total,
                "message": f"{header}\n{content}",
            }
            if truncated:
                result["truncated"] = True
            return result

        # content mode — relativize paths, return as joined string
        out_lines: list[str] = []
        for ln in lines:
            parts = ln.split(":", 2)
            if len(parts) >= 3:
                out_lines.append(f"{_rel(parts[0])}:{parts[1]}:{parts[2]}")
            elif ln.strip() == "--":
                out_lines.append("--")
            elif ln.strip():
                out_lines.append(ln)

        content = "\n".join(out_lines) if out_lines else "No matches found"
        header = f"Found {len(out_lines)} line(s) in {path}"
        if truncated:
            header += " (truncated)"
        result = {
            "path": path,
            "pattern": pattern,
            "num_lines": len(out_lines),
            "message": f"{header}\n{content}",
        }
        if truncated:
            result["truncated"] = True
        return result

    # ------------------------------------------------------------------
    # Python fallback
    # ------------------------------------------------------------------

    async def _search_python(
        self,
        resolved: Path,
        pattern: str,
        is_regex: bool,
        output_mode: str,
        glob_pat: str | None,
        file_type: str | None,
        case_insensitive: bool,
        context_lines: int,
        context_before: int,
        context_after: int,
        head_limit: int,
        offset: int,
    ) -> dict[str, Any]:
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            compiled = (
                re.compile(pattern, flags)
                if is_regex
                else re.compile(re.escape(pattern), flags)
            )
        except re.error as e:
            return {
                "error": f"Invalid regex: {e}",
                "message": f"Invalid regex pattern: {e}",
            }

        effective_limit = head_limit if head_limit > 0 else 0
        ctx_before = context_before or context_lines
        ctx_after = context_after or context_lines

        if resolved.is_file():
            matches, truncated = await asyncio.to_thread(
                self._py_search_file,
                resolved, compiled, effective_limit, ctx_before, ctx_after,
                output_mode, offset,
            )
        elif resolved.is_dir():
            matches, truncated = await asyncio.to_thread(
                self._py_search_dir,
                resolved, compiled, effective_limit, ctx_before, ctx_after,
                output_mode, offset, glob_pat, file_type,
            )
        else:
            return {
                "error": "Not a file",
                "message": f"Not a file or directory: {resolved}",
            }

        return self._build_python_result(
            str(resolved), pattern, output_mode, matches, truncated,
        )

    @staticmethod
    def _build_python_result(
        path: str,
        pattern: str,
        output_mode: str,
        matches: list[dict[str, Any]],
        truncated: bool,
    ) -> dict[str, Any]:
        base = Path(path)

        def _rel(abs_path: str) -> str:
            try:
                return str(Path(abs_path).relative_to(base))
            except ValueError:
                return abs_path

        if output_mode == "files_with_matches":
            files = [_rel(m["file"]) for m in matches]
            content = "\n".join(files) if files else "No files found"
            header = f"Found matches in {len(files)} file(s)"
            if truncated:
                header += " (truncated)"
            result: dict[str, Any] = {
                "path": path,
                "pattern": pattern,
                "num_files": len(files),
                "message": f"{header}\n{content}",
            }
        elif output_mode == "count":
            total = sum(m.get("count", 0) for m in matches)
            count_lines = [
                f"{_rel(m['file'])}:{m['count']}" for m in matches
            ]
            content = "\n".join(count_lines) if count_lines else "No matches"
            header = (
                f"Found {total} match(es) across "
                f"{len(matches)} file(s)"
            )
            if truncated:
                header += " (truncated)"
            result = {
                "path": path,
                "pattern": pattern,
                "num_files": len(matches),
                "num_matches": total,
                "message": f"{header}\n{content}",
            }
        else:
            # content mode
            out_lines: list[str] = []
            for m in matches:
                f = _rel(m.get("file", ""))
                ln = m.get("line_number", "")
                text = m.get("line", "")
                if f:
                    out_lines.append(f"{f}:{ln}:{text}")
                else:
                    out_lines.append(f"{ln}:{text}")
            content = "\n".join(out_lines) if out_lines else "No matches found"
            header = f"Found {len(out_lines)} line(s) in {path}"
            if truncated:
                header += " (truncated)"
            result = {
                "path": path,
                "pattern": pattern,
                "num_lines": len(out_lines),
                "message": f"{header}\n{content}",
            }
        if truncated:
            result["truncated"] = True
        return result

    # ------------------------------------------------------------------
    # Python fallback — single file
    # ------------------------------------------------------------------

    @staticmethod
    def _py_search_file(
        resolved: Path,
        compiled: re.Pattern,
        max_results: int,
        ctx_before: int,
        ctx_after: int,
        output_mode: str,
        offset: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        try:
            text = resolved.read_text(
                encoding="utf-8", errors="replace",
            )
            lines = text.splitlines()
        except Exception:
            return [], False

        if output_mode == "files_with_matches":
            for line in lines:
                if compiled.search(line):
                    return [{"file": str(resolved)}], False
            return [], False

        if output_mode == "count":
            count = sum(1 for line in lines if compiled.search(line))
            if count > 0:
                return [{"file": str(resolved), "count": count}], False
            return [], False

        # content mode
        matches: list[dict[str, Any]] = []
        skipped = 0
        truncated = False

        for i, line in enumerate(lines):
            if compiled.search(line):
                if skipped < offset:
                    skipped += 1
                    continue
                match: dict[str, Any] = {
                    "line_number": i + 1,
                    "line": line,
                }
                if ctx_before > 0 or ctx_after > 0:
                    start = max(0, i - ctx_before)
                    end = min(len(lines), i + ctx_after + 1)
                    match["context_before"] = lines[start:i]
                    match["context_after"] = lines[i + 1:end]
                matches.append(match)
                if max_results > 0 and len(matches) >= max_results:
                    truncated = True
                    break

        return matches, truncated

    # ------------------------------------------------------------------
    # Python fallback — directory (recursive)
    # ------------------------------------------------------------------

    @classmethod
    def _py_search_dir(
        cls,
        resolved: Path,
        compiled: re.Pattern,
        max_results: int,
        ctx_before: int,
        ctx_after: int,
        output_mode: str,
        offset: int,
        glob_pat: str | None,
        file_type: str | None,
    ) -> tuple[list[dict[str, Any]], bool]:
        matches: list[dict[str, Any]] = []
        truncated = False
        remaining = max_results
        type_exts = _TYPE_EXTENSIONS.get(file_type, ()) if file_type else ()

        for file_path in sorted(cls._walk_files(resolved)):
            # Skip hidden/VCS dirs
            if any(
                part.startswith(".")
                for part in file_path.relative_to(resolved).parts
            ):
                continue

            # Glob filter
            if glob_pat and not fnmatch.fnmatch(file_path.name, glob_pat):
                continue

            # Type filter
            if type_exts and file_path.suffix not in type_exts:
                continue

            # Binary check
            if cls._is_binary(file_path):
                continue

            file_matches, file_truncated = cls._py_search_file(
                file_path, compiled, remaining, ctx_before, ctx_after,
                output_mode, offset,
            )

            if output_mode == "content":
                for m in file_matches:
                    m["file"] = str(file_path)
            matches.extend(file_matches)

            if output_mode == "content" and remaining > 0:
                remaining -= len(file_matches)
                if remaining <= 0 or file_truncated:
                    truncated = True
                    break

        return matches, truncated

    @staticmethod
    def _walk_files(root: Path) -> list[Path]:
        """Recursively walk directory, yielding files."""
        files: list[Path] = []
        try:
            for entry in os.scandir(root):
                if entry.is_file(follow_symlinks=False):
                    files.append(Path(entry.path))
                elif entry.is_dir(follow_symlinks=False):
                    files.extend(
                        FileSearchTool._walk_files(Path(entry.path)),
                    )
        except PermissionError:
            pass
        return files

    @staticmethod
    def _is_binary(path: Path) -> bool:
        try:
            with open(path, "rb") as f:
                sample = f.read(_BINARY_SAMPLE_SIZE)
            return b"\x00" in sample
        except OSError:
            return True

    async def _request_approval(
        self, path: str, operation: str, reason: str,
    ) -> bool:
        if self._approval_callback is None:
            logger.warning(
                "file_search require_approval but no callback "
                "— denying: %s",
                path,
            )
            return False
        return await self._approval_callback(
            "file_search", path, operation, reason,
        )
