"""file_list tool — list directory contents with policy check."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from ..policy.file_access import FileAccessPolicy
from .base import ApprovalCallback, BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class FileListTool(BaseTool):
    """List directory contents on the host filesystem, subject to file access policy."""

    def __init__(
        self,
        policy: FileAccessPolicy,
        approval_callback: ApprovalCallback | None = None,
        audit_logger: Any = None,
    ) -> None:
        self._policy = policy
        self._approval_callback = approval_callback
        self._audit = audit_logger

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="file_list",
            description=(
                "List the contents of a directory. "
                "Returns file names, types, and sizes. "
                "Use this to browse directories and find files."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Absolute or ~-prefixed path to the directory to list",
                    required=True,
                ),
                ToolParameter(
                    name="show_hidden",
                    type="boolean",
                    description="Include hidden files (starting with .) (default: false)",
                    required=False,
                    default=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        path: str = kwargs["path"]
        show_hidden: bool = kwargs.get("show_hidden", False)

        # 1. Policy check (listing uses "read" operation)
        decision = self._policy.evaluate(path, "read")
        if decision.level == "deny":
            logger.warning("file_list denied: %s (%s)", path, decision.reason)
            await self._audit_op("read", path, "deny", decision.reason)
            return {
                "error": f"Access denied: {path} ({decision.reason})",
                "denied": True,
                "message": f"Cannot list {path}: {decision.reason}",
            }
        if decision.level == "require_approval" and not await self._request_approval(
            path, "read", decision.reason
        ):
                await self._audit_op("read", path, "denied_by_user", decision.reason)
                return {
                    "error": f"Approval denied: {path} ({decision.reason})",
                    "denied": True,
                    "message": f"User denied listing {path}: {decision.reason}",
                }

        resolved = Path(path).expanduser().resolve()

        if not resolved.exists():
            return {"error": "Directory not found", "message": f"Not found: {path}"}
        if not resolved.is_dir():
            return {"error": "Not a directory", "message": f"Not a directory: {path}"}

        # 2. List entries
        try:
            entries = await asyncio.to_thread(self._scan_dir, resolved, show_hidden)
        except Exception as e:
            logger.error("file_list failed: %s", e, exc_info=True)
            return {"error": str(e), "message": f"Error listing {path}: {e}"}

        logger.info("file_list: %s (%d entries)", resolved, len(entries))
        await self._audit_op("read", path, "allow", decision.reason)
        return {
            "path": str(resolved),
            "entries": entries,
            "count": len(entries),
            "message": f"Listed {resolved} ({len(entries)} entries)",
        }

    @staticmethod
    def _scan_dir(resolved: Path, show_hidden: bool) -> list[dict[str, Any]]:
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
                        "size": stat.st_size if entry.is_file() else None,
                    })
                except OSError:
                    entries.append({
                        "name": entry.name,
                        "type": "unknown",
                        "size": None,
                    })
        return entries

    async def _request_approval(self, path: str, operation: str, reason: str) -> bool:
        if self._approval_callback is None:
            logger.warning(
                "file_list require_approval but no callback — denying: %s", path,
            )
            return False
        return await self._approval_callback("file_list", path, operation, reason)

    async def _audit_op(self, operation: str, path: str, decision: str, reason: str) -> None:
        if self._audit is not None:
            await self._audit.log_file_op(operation, path, decision, reason)
