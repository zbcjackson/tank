"""file_delete tool — delete file with policy check and auto-backup."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ..policy.backup import BackupManager
from ..policy.file_access import FileAccessPolicy
from .base import ApprovalCallback, BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class FileDeleteTool(BaseTool):
    """Delete a file on the host filesystem, subject to file access policy."""

    def __init__(
        self,
        policy: FileAccessPolicy,
        backup: BackupManager,
        approval_callback: ApprovalCallback | None = None,
        audit_logger: Any = None,
    ) -> None:
        self._policy = policy
        self._backup = backup
        self._approval_callback = approval_callback
        self._audit = audit_logger

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

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        path: str = kwargs["path"]

        # 1. Policy check
        decision = self._policy.evaluate(path, "delete")
        if decision.level == "deny":
            logger.warning("file_delete denied: %s (%s)", path, decision.reason)
            await self._audit_op("delete", path, "deny", decision.reason)
            return {
                "error": f"Access denied: {path} ({decision.reason})",
                "denied": True,
                "message": f"Cannot delete {path}: {decision.reason}",
            }
        if decision.level == "require_approval" and not await self._request_approval(
            path, "delete", decision.reason
        ):
                await self._audit_op("delete", path, "denied_by_user", decision.reason)
                return {
                    "error": f"Approval denied: {path} ({decision.reason})",
                    "denied": True,
                    "message": f"User denied deleting {path}: {decision.reason}",
                }

        resolved = Path(path).expanduser().resolve()

        if not resolved.exists():
            return {"error": "File not found", "message": f"File not found: {path}"}
        if not resolved.is_file():
            return {"error": "Not a file", "message": f"Not a file: {path}"}

        # 2. Backup before delete
        backup_path = await self._backup.snapshot(str(resolved))

        # 3. Delete
        try:
            await asyncio.to_thread(resolved.unlink)
        except Exception as e:
            logger.error("file_delete failed: %s", e, exc_info=True)
            return {"error": str(e), "message": f"Error deleting {path}: {e}"}

        logger.info("file_delete: %s", resolved)
        await self._audit_op("delete", path, "allow", decision.reason)
        result: dict[str, Any] = {
            "path": str(resolved),
            "message": f"Deleted {resolved}",
        }
        if backup_path:
            result["backup_path"] = backup_path
            result["message"] += f" (backup: {backup_path})"
        return result

    async def _request_approval(self, path: str, operation: str, reason: str) -> bool:
        if self._approval_callback is None:
            logger.warning(
                "file_delete require_approval but no callback — denying: %s", path,
            )
            return False
        return await self._approval_callback("file_delete", path, operation, reason)

    async def _audit_op(self, operation: str, path: str, decision: str, reason: str) -> None:
        if self._audit is not None:
            await self._audit.log_file_op(operation, path, decision, reason)
