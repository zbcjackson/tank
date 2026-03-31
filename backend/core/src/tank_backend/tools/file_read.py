"""file_read tool — read file contents with policy check."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ..policy.file_access import FileAccessPolicy
from .base import ApprovalCallback, BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class FileReadTool(BaseTool):
    """Read a file on the host filesystem, subject to file access policy."""

    def __init__(
        self,
        policy: FileAccessPolicy,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self._policy = policy
        self._approval_callback = approval_callback

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="file_read",
            description=(
                "Read the contents of a file on the host filesystem. "
                "Use this tool (not sandbox_exec) for reading files — "
                "it enforces access policy and protects sensitive paths."
            ),
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Absolute or ~-prefixed path to the file to read",
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

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        path: str = kwargs["path"]
        encoding: str = kwargs.get("encoding", "utf-8")

        # 1. Policy check
        decision = self._policy.evaluate(path, "read")
        if decision.level == "deny":
            logger.warning("file_read denied: %s (%s)", path, decision.reason)
            return {
                "error": f"Access denied: {path} ({decision.reason})",
                "denied": True,
                "message": f"Cannot read {path}: {decision.reason}",
            }
        if decision.level == "require_approval":
            if not await self._request_approval(path, "read", decision.reason):
                return {
                    "error": f"Approval denied: {path} ({decision.reason})",
                    "denied": True,
                    "message": f"User denied reading {path}: {decision.reason}",
                }

        # 2. Read file
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return {"error": "File not found", "message": f"File not found: {path}"}
        if not resolved.is_file():
            return {"error": "Not a file", "message": f"Not a file: {path}"}

        try:
            content = await asyncio.to_thread(resolved.read_text, encoding)
        except Exception as e:
            logger.error("file_read failed: %s", e, exc_info=True)
            return {"error": str(e), "message": f"Error reading {path}: {e}"}

        logger.info("file_read: %s (%d chars)", resolved, len(content))
        return {
            "path": str(resolved),
            "content": content,
            "size": len(content),
            "message": f"Read {resolved} ({len(content)} chars)",
        }

    async def _request_approval(self, path: str, operation: str, reason: str) -> bool:
        """Request path-specific approval. Returns False if no callback or denied."""
        if self._approval_callback is None:
            logger.warning(
                "file_read require_approval but no callback — denying: %s", path,
            )
            return False
        return await self._approval_callback("file_read", path, operation, reason)
