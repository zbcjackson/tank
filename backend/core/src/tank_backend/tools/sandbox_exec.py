"""sandbox_exec tool — one-shot command execution in Docker sandbox."""

from __future__ import annotations

import logging
from typing import Any

from ..sandbox.manager import SandboxManager
from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class SandboxExecTool(BaseTool):
    """Run a command to completion inside the sandbox container."""

    def __init__(self, sandbox: SandboxManager) -> None:
        self._sandbox = sandbox

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="sandbox_exec",
            description=(
                "Execute a shell command inside a sandboxed Docker container. "
                "The command runs to completion and returns stdout, stderr, and exit code. "
                "Each call gets a fresh shell process, but filesystem changes persist "
                "across calls within the same session. "
                "Use for one-shot commands like ls, curl, python script.py, pip install, etc."
            ),
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description="Shell command to execute (e.g. 'ls -la', 'python script.py')",
                    required=True,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Max execution time in seconds (default: 120, max: 600)",
                    required=False,
                    default=120,
                ),
                ToolParameter(
                    name="working_dir",
                    type="string",
                    description="Working directory inside the container (default: /workspace)",
                    required=False,
                    default="/workspace",
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        command: str = kwargs["command"]
        timeout: int = kwargs.get("timeout", 120)
        working_dir: str = kwargs.get("working_dir", "/workspace")

        logger.info("sandbox_exec: %s (timeout=%ds, cwd=%s)", command, timeout, working_dir)

        try:
            result = await self._sandbox.exec_command(
                command=command,
                timeout=timeout,
                working_dir=working_dir,
            )
            data = result.to_dict()
            parts = [
                result.stdout if result.stdout else None,
                f"[stderr] {result.stderr}" if result.stderr else None,
                "[command timed out]" if result.timed_out else None,
            ]
            data["message"] = "\n".join(p for p in parts if p) or "(no output)"
            return data

        except Exception as e:
            logger.error("sandbox_exec failed: %s", e, exc_info=True)
            return {"error": str(e), "message": f"Sandbox exec error: {e}"}
