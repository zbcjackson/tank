"""file_delete tool — delete file with policy check and auto-backup."""

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


class FileDeleteTool(BaseTool):
    """Delete a file on the host filesystem, subject to file access policy."""

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
            name="file_delete",
            description=(
                "Delete a file. "
                "Automatically backs up the file before deleting. "
                "Use this for deleting files — it enforces access policy "
                "and creates backups."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Absolute or ~-prefixed path to the file to delete",
                    required=True,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        path: str = kwargs["path"]

        # 1. Policy check
        decision = self._policy.evaluate(path, "delete")
        if decision.level == "deny":
            logger.warning("file_delete denied: %s (%s)", path, decision.reason)
            return ToolResult(
                content=json.dumps(
                    {"error": f"Access denied: {path} ({decision.reason})", "denied": True},
                    ensure_ascii=False,
                ),
                display=f"Cannot delete {path}: {decision.reason}",
                error=True,
            )
        if decision.level == "require_approval" and not await self._request_approval(
            path, "delete", decision.reason
        ):
            return ToolResult(
                content=json.dumps(
                    {"error": f"Approval denied: {path} ({decision.reason})", "denied": True},
                    ensure_ascii=False,
                ),
                display=f"User denied deleting {path}: {decision.reason}",
                error=True,
            )

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

        # 2. Backup before delete
        backup_path = await self._backup.snapshot(str(resolved))

        # 3. Delete
        try:
            await asyncio.to_thread(resolved.unlink)
        except Exception as e:
            logger.error("file_delete failed: %s", e, exc_info=True)
            return ToolResult(
                content=json.dumps({"error": str(e)}, ensure_ascii=False),
                display=f"Error deleting {path}: {e}",
                error=True,
            )

        logger.info("file_delete: %s", resolved)
        data: dict[str, Any] = {"path": str(resolved)}
        display = f"Deleted {resolved}"
        if backup_path:
            data["backup_path"] = backup_path
            display += f" (backup: {backup_path})"
        return ToolResult(
            content=json.dumps(data, ensure_ascii=False),
            display=display,
        )

    async def _request_approval(self, path: str, operation: str, reason: str) -> bool:
        if self._approval_callback is None:
            logger.warning(
                "file_delete require_approval but no callback — denying: %s", path,
            )
            return False
        return await self._approval_callback("file_delete", path, operation, reason)
