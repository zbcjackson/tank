"""file_read tool — read file contents with policy check."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ..policy.file_access import FileAccessPolicy
from .base import ApprovalCallback, BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)

# Default max file size (1 MB)
DEFAULT_MAX_SIZE = 1_048_576
# Sample size for binary detection
_BINARY_SAMPLE_SIZE = 8192


class FileReadTool(BaseTool):
    """Read a file on the host filesystem, subject to file access policy."""

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
            name="file_read",
            description=(
                "Read the contents of a text file. "
                "Use this for reading files — it enforces access policy "
                "and protects sensitive paths. "
                "Binary files are detected and rejected. "
                "Large files can be read in portions using offset and limit."
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
                ToolParameter(
                    name="max_size",
                    type="integer",
                    description="Max file size in bytes (default: 1048576 = 1MB). "
                                "Files larger than this are rejected unless offset/limit is used.",
                    required=False,
                    default=DEFAULT_MAX_SIZE,
                ),
                ToolParameter(
                    name="offset",
                    type="integer",
                    description="Start reading from this line number (0-based, default: 0)",
                    required=False,
                    default=0,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Max number of lines to read (default: all lines)",
                    required=False,
                    default=None,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        path: str = kwargs["path"]
        encoding: str = kwargs.get("encoding", "utf-8")
        max_size: int = kwargs.get("max_size", DEFAULT_MAX_SIZE) or DEFAULT_MAX_SIZE
        offset: int = kwargs.get("offset", 0) or 0
        limit: int | None = kwargs.get("limit")

        # 1. Policy check
        decision = self._policy.evaluate(path, "read")
        if decision.level == "deny":
            logger.warning("file_read denied: %s (%s)", path, decision.reason)
            await self._audit_op("read", path, "deny", decision.reason)
            return {
                "error": f"Access denied: {path} ({decision.reason})",
                "denied": True,
                "message": f"Cannot read {path}: {decision.reason}",
            }
        if decision.level == "require_approval" and not await self._request_approval(
            path, "read", decision.reason
        ):
                await self._audit_op("read", path, "denied_by_user", decision.reason)
                return {
                    "error": f"Approval denied: {path} ({decision.reason})",
                    "denied": True,
                    "message": f"User denied reading {path}: {decision.reason}",
                }

        # 2. Validate path
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return {"error": "File not found", "message": f"File not found: {path}"}
        if not resolved.is_file():
            return {"error": "Not a file", "message": f"Not a file: {path}"}

        # 3. Check file size
        try:
            stat = resolved.stat()
        except OSError as e:
            return {"error": str(e), "message": f"Cannot stat {path}: {e}"}

        has_range = offset > 0 or limit is not None
        if stat.st_size > max_size and not has_range:
            return {
                "error": "File too large",
                "size": stat.st_size,
                "max_size": max_size,
                "message": (
                    f"File is {stat.st_size:,} bytes (max {max_size:,}). "
                    f"Use offset/limit to read a portion, or increase max_size."
                ),
            }

        # 4. Binary detection
        try:
            sample = await asyncio.to_thread(self._read_sample, resolved)
            if b"\x00" in sample:
                return {
                    "error": "Binary file",
                    "size": stat.st_size,
                    "message": (
                        f"File appears to be binary ({stat.st_size:,} bytes). "
                        f"Cannot read as text."
                    ),
                }
        except OSError as e:
            return {"error": str(e), "message": f"Cannot read {path}: {e}"}

        # 5. Read file
        try:
            content = await asyncio.to_thread(
                self._read_text, resolved, encoding, offset, limit,
            )
        except Exception as e:
            logger.error("file_read failed: %s", e, exc_info=True)
            return {"error": str(e), "message": f"Error reading {path}: {e}"}

        result: dict[str, Any] = {
            "path": str(resolved),
            "content": content,
            "size": len(content),
            "file_size": stat.st_size,
            "message": f"Read {resolved} ({len(content)} chars)",
        }
        if offset > 0:
            result["offset"] = offset
        if limit is not None:
            result["limit"] = limit
        logger.info("file_read: %s (%d chars)", resolved, len(content))
        await self._audit_op("read", path, "allow", decision.reason)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_sample(resolved: Path, size: int = _BINARY_SAMPLE_SIZE) -> bytes:
        with open(resolved, "rb") as f:
            return f.read(size)

    @staticmethod
    def _read_text(
        resolved: Path, encoding: str, offset: int, limit: int | None,
    ) -> str:
        with open(resolved, encoding=encoding) as f:
            if offset == 0 and limit is None:
                return f.read()
            lines: list[str] = []
            for i, line in enumerate(f):
                if i < offset:
                    continue
                lines.append(line)
                if limit is not None and len(lines) >= limit:
                    break
            return "".join(lines)

    async def _request_approval(self, path: str, operation: str, reason: str) -> bool:
        """Request path-specific approval. Returns False if no callback or denied."""
        if self._approval_callback is None:
            logger.warning(
                "file_read require_approval but no callback — denying: %s", path,
            )
            return False
        return await self._approval_callback("file_read", path, operation, reason)

    async def _audit_op(self, operation: str, path: str, decision: str, reason: str) -> None:
        if self._audit is not None:
            await self._audit.log_file_op(operation, path, decision, reason)
