"""sandbox_exec tool — one-shot command execution in sandbox."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class SandboxExecTool(BaseTool):
    """Run a command inside the sandbox, either to completion or in the background."""

    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="run_command",
            description=(
                "Run a shell command on the user's machine. "
                "The command can access the user's home directory and files. "
                "Returns stdout, stderr, and exit code. "
                "Set background=true to start a long-running process and get a process ID "
                "back immediately — then use manage_process to poll output or kill it. "
                "Use for: system info (du, df, top, ps, uname, uptime, free), "
                "file operations (ls, find, cat, grep, wc), "
                "development (python, node, git, pip, npm), "
                "and any other shell command the user asks to run."
            ),
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description="Shell command to execute (e.g. 'ls -la ~', 'python script.py')",
                    required=True,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description=(
                        "Max execution time in seconds (default: 120, max: 600). "
                        "Ignored when background=true."
                    ),
                    required=False,
                    default=120,
                ),
                ToolParameter(
                    name="working_dir",
                    type="string",
                    description=(
                        "Working directory for the command"
                        " (default: user's home directory)"
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="background",
                    type="boolean",
                    description=(
                        "Start the command in the background and return a "
                        "process ID immediately (default: false)"
                    ),
                    required=False,
                    default=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        command: str = kwargs["command"]
        timeout: int = kwargs.get("timeout", 120)
        working_dir: str = kwargs.get("working_dir") or str(Path.home())
        background: bool = kwargs.get("background", False)

        logger.info(
            "run_command: %s (timeout=%ds, cwd=%s, bg=%s)",
            command, timeout, working_dir, background,
        )

        try:
            result = await self._sandbox.exec_command(
                command=command,
                timeout=timeout,
                working_dir=working_dir,
                background=background,
            )

            data = result.to_dict()

            if background:
                data["process_id"] = result.stdout
                data["message"] = (
                    f"Process started in background (id: {result.stdout}). "
                    "Use manage_process to poll output or kill it."
                )
            else:
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
