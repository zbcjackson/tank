"""file_write tool — write file contents with policy check and auto-backup."""

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


class FileWriteTool(BaseTool):
    """Write a file on the host filesystem, subject to file access policy."""

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
            name="file_write",
            description=(
                "Write content to a file. "
                "Creates parent directories if needed. "
                "Automatically backs up existing files before overwriting. "
                "Use this for writing files — it enforces access policy "
                "and creates backups."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Absolute or ~-prefixed path to the file to write",
                    required=True,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Content to write to the file",
                    required=True,
                ),
                ToolParameter(
                    name="encoding",
                    type="string",
                    description="File encoding (default: utf-8)",
                    required=False,
                    default="utf-8",
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        path: str = kwargs["path"]
        content: str = kwargs["content"]
        encoding: str = kwargs.get("encoding", "utf-8")

        # 1. Policy check
        decision = self._policy.evaluate(path, "write")
        if decision.level == "deny":
            logger.warning("file_write denied: %s (%s)", path, decision.reason)
            return ToolResult(
                content=json.dumps(
                    {"error": f"Access denied: {path} ({decision.reason})", "denied": True},
                    ensure_ascii=False,
                ),
                display=f"Cannot write {path}: {decision.reason}",
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
                display=f"User denied writing {path}: {decision.reason}",
                error=True,
            )

        resolved = Path(path).expanduser().resolve()

        # 2. Backup existing file
        backup_path = await self._backup.snapshot(str(resolved))

        # 3. Write file
        try:
            await asyncio.to_thread(self._do_write, resolved, content, encoding)
        except Exception as e:
            logger.error("file_write failed: %s", e, exc_info=True)
            return ToolResult(
                content=json.dumps({"error": str(e)}, ensure_ascii=False),
                display=f"Error writing {path}: {e}",
                error=True,
            )

        logger.info("file_write: %s (%d chars)", resolved, len(content))
        payload: dict[str, Any] = {
            "path": str(resolved),
            "size": len(content),
        }
        display = f"Wrote {resolved} ({len(content)} chars)"
        if backup_path:
            payload["backup_path"] = backup_path
            display += f" (backup: {backup_path})"
        return ToolResult(
            content=json.dumps(payload, ensure_ascii=False),
            display=display,
        )

    @staticmethod
    def _do_write(resolved: Path, content: str, encoding: str) -> None:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding=encoding)

    async def _request_approval(self, path: str, operation: str, reason: str) -> bool:
        if self._approval_callback is None:
            logger.warning(
                "file_write require_approval but no callback — denying: %s", path,
            )
            return False
        return await self._approval_callback("file_write", path, operation, reason)
