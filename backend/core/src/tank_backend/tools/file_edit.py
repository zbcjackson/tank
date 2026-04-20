"""file_edit tool — string replacement and line insertion with policy check and auto-backup."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from ..policy.backup import BackupManager
from ..policy.file_access import FileAccessPolicy
from .base import ApprovalCallback, BaseTool, ToolInfo, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class FileEditTool(BaseTool):
    """Replace a string in a file or insert text at a line position.

    **Replace mode** (default): ``old_string`` must appear exactly once
    (unique match).  Use ``replace_all=True`` to replace every occurrence.

    **Insert mode**: set ``old_string=""`` and provide ``insert_after_line``
    to insert ``new_string`` after the given line number (0 = beginning).
    """

    def __init__(
        self,
        policy: FileAccessPolicy,
        backup: BackupManager,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self._policy = policy
        self._backup = backup
        self._approval_callback = approval_callback

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="file_edit",
            description=(
                "Edit a file by replacing a string or inserting text at a line. "
                "Replace mode: old_string must appear exactly once (unique match). "
                "Set replace_all to true to replace every occurrence. "
                "Insert mode: set old_string to empty and provide "
                "insert_after_line to insert new_string after that line "
                "(0 = beginning of file). "
                "Automatically backs up the file before editing."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description=(
                        "Absolute or ~-prefixed path to the file to edit"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="old_string",
                    type="string",
                    description=(
                        "The exact string to find and replace. "
                        "Set to empty string for insert mode."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="new_string",
                    type="string",
                    description=(
                        "The replacement string, or the text to insert"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="insert_after_line",
                    type="integer",
                    description=(
                        "Insert new_string after this line number "
                        "(0 = beginning of file). "
                        "Only used when old_string is empty."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="encoding",
                    type="string",
                    description="File encoding (default: utf-8)",
                    required=False,
                    default="utf-8",
                ),
                ToolParameter(
                    name="replace_all",
                    type="boolean",
                    description=(
                        "Replace all occurrences instead of requiring "
                        "a unique match (default: false)"
                    ),
                    required=False,
                    default=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        path: str = kwargs["path"]
        old_string: str = kwargs["old_string"]
        new_string: str = kwargs["new_string"]
        encoding: str = kwargs.get("encoding", "utf-8")
        replace_all: bool = kwargs.get("replace_all", False)
        insert_after_line: int | None = kwargs.get("insert_after_line")

        # Determine mode
        is_insert = old_string == "" and insert_after_line is not None

        # 1. Validate inputs
        if old_string == "" and insert_after_line is None:
            return ToolResult(
                content=json.dumps({"error": "Invalid parameters"}, ensure_ascii=False),
                display=(
                    "old_string is empty but insert_after_line not provided. "
                    "For insert mode, set insert_after_line. "
                    "For replace mode, provide a non-empty old_string."
                ),
                error=True,
            )
        if is_insert:
            if insert_after_line < 0:
                return ToolResult(
                    content=json.dumps(
                        {"error": "Invalid line number"}, ensure_ascii=False,
                    ),
                    display="insert_after_line must be >= 0.",
                    error=True,
                )
            if new_string == "":
                return ToolResult(
                    content=json.dumps(
                        {"error": "Empty insert"}, ensure_ascii=False,
                    ),
                    display="new_string must not be empty for insert mode.",
                    error=True,
                )
        elif old_string == new_string:
            return ToolResult(
                content=json.dumps({"error": "No-op edit"}, ensure_ascii=False),
                display=(
                    "old_string and new_string are identical "
                    "— nothing to do."
                ),
                error=True,
            )

        # 2. Policy check (editing is a write operation)
        decision = self._policy.evaluate(path, "write")
        if decision.level == "deny":
            logger.warning("file_edit denied: %s (%s)", path, decision.reason)
            return ToolResult(
                content=json.dumps(
                    {"error": f"Access denied: {path} ({decision.reason})", "denied": True},
                    ensure_ascii=False,
                ),
                display=f"Cannot edit {path}: {decision.reason}",
                error=True,
            )
        if decision.level == "require_approval" and not await self._request_approval(
            path, "write", decision.reason
        ):
            return ToolResult(
                content=json.dumps(
                    {"error": f"Approval denied: {path} ({decision.reason})", "denied": True},
                    ensure_ascii=False,
                ),
                display=f"User denied editing {path}: {decision.reason}",
                error=True,
            )

        # 3. Validate path
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return ToolResult(
                content=json.dumps({"error": "File not found"}, ensure_ascii=False),
                display=f"File not found: {path}",
                error=True,
            )
        if not resolved.is_file():
            return ToolResult(
                content=json.dumps({"error": "Not a file"}, ensure_ascii=False),
                display=f"Not a file: {path}",
                error=True,
            )

        # 4. Read current content
        try:
            content = await asyncio.to_thread(resolved.read_text, encoding)
        except Exception as e:
            logger.error("file_edit read failed: %s", e, exc_info=True)
            return ToolResult(
                content=json.dumps({"error": str(e)}, ensure_ascii=False),
                display=f"Error reading {path}: {e}",
                error=True,
            )

        # 5. Backup before edit
        backup_path = await self._backup.snapshot(str(resolved))

        # 6. Apply edit
        if is_insert:
            new_content = self._insert_at_line(
                content, new_string, insert_after_line,
            )
        else:
            # Replace mode — check match count
            count = content.count(old_string)
            if count == 0:
                return ToolResult(
                    content=json.dumps(
                        {"error": "String not found"}, ensure_ascii=False,
                    ),
                    display=f"old_string not found in {path}",
                    error=True,
                )
            if count > 1 and not replace_all:
                return ToolResult(
                    content=json.dumps(
                        {"error": "Ambiguous match"}, ensure_ascii=False,
                    ),
                    display=(
                        f"old_string found {count} times in {path} — "
                        f"provide more context to make it unique, "
                        f"or set replace_all=true to replace all."
                    ),
                    error=True,
                )
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

        # 7. Write
        try:
            await asyncio.to_thread(resolved.write_text, new_content, encoding)
        except Exception as e:
            logger.error("file_edit write failed: %s", e, exc_info=True)
            return ToolResult(
                content=json.dumps({"error": str(e)}, ensure_ascii=False),
                display=f"Error writing {path}: {e}",
                error=True,
            )

        # 8. Build result
        if is_insert:
            logger.info(
                "file_edit insert: %s after line %d", resolved, insert_after_line,
            )
            data: dict[str, Any] = {
                "path": str(resolved),
                "insert_after_line": insert_after_line,
            }
            display = (
                f"Inserted text in {resolved} after line "
                f"{insert_after_line}"
            )
        else:
            n = count if replace_all else 1
            logger.info("file_edit: %s (%d replacements)", resolved, n)
            data = {
                "path": str(resolved),
                "replacements": n,
            }
            display = f"Edited {resolved} ({n} replacement(s))"

        if backup_path:
            data["backup_path"] = backup_path
            display += f" (backup: {backup_path})"
        return ToolResult(
            content=json.dumps(data, ensure_ascii=False),
            display=display,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _insert_at_line(content: str, text: str, after_line: int) -> str:
        """Insert text after the given line number (0 = prepend)."""
        lines = content.splitlines(keepends=True)
        # Clamp to valid range
        pos = min(after_line, len(lines))
        lines.insert(pos, text)
        return "".join(lines)

    async def _request_approval(self, path: str, operation: str, reason: str) -> bool:
        if self._approval_callback is None:
            logger.warning(
                "file_edit require_approval but no callback — denying: %s", path,
            )
            return False
        return await self._approval_callback("file_edit", path, operation, reason)
