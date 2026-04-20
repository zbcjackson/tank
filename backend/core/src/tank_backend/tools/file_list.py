"""file_list tool — list/find directory contents with policy check.

Uses ripgrep (``rg --files``) for glob search when available,
falling back to Python ``os.walk`` + ``fnmatch``.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
from pathlib import Path
from typing import Any

from ..policy.file_access import FileAccessPolicy
from .base import ApprovalCallback, BaseTool, ToolInfo, ToolParameter, ToolResult
from .ripgrep import find_rg_binary, run_rg_files

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RESULTS = 200


class FileListTool(BaseTool):
    """List or find files/directories, subject to file access policy.

    Without a glob pattern, lists the immediate contents of a directory.
    With a glob pattern, recursively finds matching files and directories.
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
            logger.info("file_list: using ripgrep at %s", self._rg_binary)
        else:
            logger.info(
                "file_list: ripgrep not found, using Python fallback",
            )

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="file_list",
            description=(
                "List or find files and directories. "
                "Without a glob pattern, lists immediate directory "
                "contents. With a glob pattern, recursively finds "
                "matching files and directories by name. "
                "Use this to browse directories, find files by name, "
                "or locate folders."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description=(
                        "Absolute or ~-prefixed path to the directory"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="glob",
                    type="string",
                    description=(
                        "Glob pattern to match file/directory names "
                        "(e.g. '*.py', '*教材*'). "
                        "When provided, searches recursively. "
                        "Supports * and ? wildcards."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="show_hidden",
                    type="boolean",
                    description=(
                        "Include hidden files/dirs starting with . "
                        "(default: false)"
                    ),
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description=(
                        "Max results for glob search "
                        f"(default: {_DEFAULT_MAX_RESULTS})"
                    ),
                    required=False,
                    default=_DEFAULT_MAX_RESULTS,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        path: str = kwargs["path"]
        show_hidden: bool = kwargs.get("show_hidden", False)
        glob_pat: str | None = kwargs.get("glob")
        max_results: int = (
            kwargs.get("max_results", _DEFAULT_MAX_RESULTS)
            or _DEFAULT_MAX_RESULTS
        )

        # 1. Policy check (listing uses "read" operation)
        decision = self._policy.evaluate(path, "read")
        if decision.level == "deny":
            logger.warning(
                "file_list denied: %s (%s)", path, decision.reason,
            )
            return ToolResult(
                content=json.dumps(
                    {"error": f"Access denied: {path} ({decision.reason})", "denied": True},
                    ensure_ascii=False,
                ),
                display=f"Cannot list {path}: {decision.reason}",
                error=True,
            )
        if (
            decision.level == "require_approval"
            and not await self._request_approval(
                path, "read", decision.reason,
            )
        ):
            return ToolResult(
                content=json.dumps(
                    {"error": f"Approval denied: {path} ({decision.reason})", "denied": True},
                    ensure_ascii=False,
                ),
                display=f"User denied listing {path}: {decision.reason}",
                error=True,
            )

        resolved = Path(path).expanduser().resolve()

        if not resolved.exists():
            return ToolResult(
                content=json.dumps({"error": "Directory not found"}, ensure_ascii=False),
                display=f"Not found: {path}",
                error=True,
            )
        if not resolved.is_dir():
            return ToolResult(
                content=json.dumps({"error": "Not a directory"}, ensure_ascii=False),
                display=f"Not a directory: {path}",
                error=True,
            )

        # 2. Dispatch: glob search vs flat listing
        try:
            if glob_pat:
                if self._rg_binary:
                    return await self._glob_ripgrep(
                        resolved, glob_pat, show_hidden, max_results,
                    )
                entries, truncated = await asyncio.to_thread(
                    self._glob_python,
                    resolved, glob_pat, show_hidden, max_results,
                )
                logger.info(
                    "file_list glob: %s pattern=%r (%d entries)",
                    resolved, glob_pat, len(entries),
                )
                data: dict[str, Any] = {
                    "path": str(resolved),
                    "glob": glob_pat,
                    "entries": entries,
                    "count": len(entries),
                }
                if truncated:
                    data["truncated"] = True
                return ToolResult(
                    content=json.dumps(data, ensure_ascii=False),
                    display=self._format_entries_message(
                        f"Found {len(entries)} match(es) in {resolved}",
                        entries, truncated,
                    ),
                )

            entries = await asyncio.to_thread(
                self._scan_dir, resolved, show_hidden,
            )
        except Exception as e:
            logger.error("file_list failed: %s", e, exc_info=True)
            return ToolResult(
                content=json.dumps({"error": str(e)}, ensure_ascii=False),
                display=f"Error listing {path}: {e}",
                error=True,
            )

        logger.info(
            "file_list: %s (%d entries)", resolved, len(entries),
        )
        return ToolResult(
            content=json.dumps(
                {"path": str(resolved), "entries": entries, "count": len(entries)},
                ensure_ascii=False,
            ),
            display=self._format_entries_message(
                f"Listed {resolved} ({len(entries)} entries)", entries,
            ),
        )

    # ------------------------------------------------------------------
    # Flat directory listing (existing behavior)
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_dir(
        resolved: Path, show_hidden: bool,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        with os.scandir(resolved) as it:
            for entry in sorted(it, key=lambda e: e.name):
                if not show_hidden and entry.name.startswith("."):
                    continue
                try:
                    stat = entry.stat()
                    entries.append({
                        "name": entry.name,
                        "type": "dir" if entry.is_dir() else "file",
                        "size": (
                            stat.st_size if entry.is_file() else None
                        ),
                    })
                except OSError:
                    entries.append({
                        "name": entry.name,
                        "type": "unknown",
                        "size": None,
                    })
        return entries

    # ------------------------------------------------------------------
    # Recursive glob search — ripgrep path
    # ------------------------------------------------------------------

    async def _glob_ripgrep(
        self,
        resolved: Path,
        pattern: str,
        show_hidden: bool,
        max_results: int,
    ) -> ToolResult:
        """Use ``rg --files --glob`` for files + dir name scan.

        ``rg --files`` only lists files, not directories. We supplement
        with a lightweight directory-name-only walk so that searching
        for ``*教材*`` finds a folder named ``教材``.
        """
        # 1. rg --files for file matches (fast)
        rg_result = await run_rg_files(
            self._rg_binary,
            str(resolved),
            glob=pattern,
            show_hidden=show_hidden,
            head_limit=max_results,
        )

        entries: list[dict[str, Any]] = []
        truncated = False

        if rg_result.error:
            logger.warning(
                "file_list rg --files failed, falling back: %s",
                rg_result.error,
            )
            entries, truncated = await asyncio.to_thread(
                self._glob_python,
                resolved, pattern, show_hidden, max_results,
            )
        else:
            # 2. Scan directory names (rg --files skips dirs)
            dir_entries = await asyncio.to_thread(
                self._find_matching_dirs,
                resolved, pattern, show_hidden, max_results,
            )
            entries.extend(dir_entries)

            # 3. Parse rg file results
            remaining = max_results - len(entries)
            for line in rg_result.lines:
                if remaining <= 0:
                    truncated = True
                    break
                line = line.strip()
                if not line:
                    continue
                p = Path(line)
                try:
                    rel = str(p.relative_to(resolved))
                except ValueError:
                    rel = p.name
                entry: dict[str, Any] = {
                    "name": p.name,
                    "path": str(p),
                    "relative_path": rel,
                    "type": "file",
                }
                try:
                    entry["size"] = p.stat().st_size
                except OSError:
                    entry["size"] = None
                entries.append(entry)
                remaining -= 1

            if rg_result.truncated and not truncated:
                truncated = True

        logger.info(
            "file_list glob (rg): %s pattern=%r (%d entries)",
            resolved, pattern, len(entries),
        )
        data: dict[str, Any] = {
            "path": str(resolved),
            "glob": pattern,
            "entries": entries,
            "count": len(entries),
        }
        if truncated:
            data["truncated"] = True
        return ToolResult(
            content=json.dumps(data, ensure_ascii=False),
            display=self._format_entries_message(
                f"Found {len(entries)} match(es) in {resolved}",
                entries, truncated,
            ),
        )

    @staticmethod
    def _find_matching_dirs(
        root: Path,
        pattern: str,
        show_hidden: bool,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Recursively find directories matching a glob pattern.

        Lightweight — only checks directory names, never reads files.
        """
        entries: list[dict[str, Any]] = []

        for dirpath, dirnames, _ in os.walk(root):
            if not show_hidden:
                dirnames[:] = [
                    d for d in dirnames if not d.startswith(".")
                ]
            rel_dir = os.path.relpath(dirpath, root)

            for dname in sorted(dirnames):
                if fnmatch.fnmatch(dname, pattern):
                    full = os.path.join(dirpath, dname)
                    entries.append({
                        "name": dname,
                        "path": full,
                        "relative_path": (
                            os.path.join(rel_dir, dname)
                            if rel_dir != "."
                            else dname
                        ),
                        "type": "dir",
                    })
                    if len(entries) >= max_results:
                        return entries

        return entries

    # ------------------------------------------------------------------
    # Recursive glob search — Python fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _glob_python(
        root: Path,
        pattern: str,
        show_hidden: bool,
        max_results: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Recursively find files/dirs matching a glob pattern."""
        entries: list[dict[str, Any]] = []
        truncated = False

        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden directories
            if not show_hidden:
                dirnames[:] = [
                    d for d in dirnames if not d.startswith(".")
                ]

            rel_dir = os.path.relpath(dirpath, root)

            # Check directory names
            for dname in sorted(dirnames):
                if fnmatch.fnmatch(dname, pattern):
                    full = os.path.join(dirpath, dname)
                    entries.append({
                        "name": dname,
                        "path": full,
                        "relative_path": os.path.join(rel_dir, dname)
                        if rel_dir != "."
                        else dname,
                        "type": "dir",
                    })
                    if len(entries) >= max_results:
                        return entries, True

            # Check file names
            for fname in sorted(filenames):
                if not show_hidden and fname.startswith("."):
                    continue
                if fnmatch.fnmatch(fname, pattern):
                    full = os.path.join(dirpath, fname)
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = None
                    entries.append({
                        "name": fname,
                        "path": full,
                        "relative_path": os.path.join(rel_dir, fname)
                        if rel_dir != "."
                        else fname,
                        "type": "file",
                        "size": size,
                    })
                    if len(entries) >= max_results:
                        return entries, True

        return entries, truncated

    async def _request_approval(
        self, path: str, operation: str, reason: str,
    ) -> bool:
        if self._approval_callback is None:
            logger.warning(
                "file_list require_approval but no callback "
                "— denying: %s",
                path,
            )
            return False
        return await self._approval_callback(
            "file_list", path, operation, reason,
        )

    # ------------------------------------------------------------------
    # Message formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_entries_message(
        header: str,
        entries: list[dict[str, Any]],
        truncated: bool = False,
    ) -> str:
        """Build a human-friendly listing used as ``ToolResult.display``.

        The full structured data is in ``ToolResult.content`` (JSON);
        this formatted string is what the UI shows to the user.
        """
        if truncated:
            header += " (truncated)"
        if not entries:
            return header
        lines = [header]
        for e in entries:
            etype = e.get("type", "file")
            name = e.get("relative_path") or e.get("name", "")
            size = e.get("size")
            if etype == "dir":
                lines.append(f"  [dir]  {name}")
            elif size is not None:
                lines.append(f"  [file] {name} ({size}B)")
            else:
                lines.append(f"  [file] {name}")
        return "\n".join(lines)
