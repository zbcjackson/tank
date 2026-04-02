"""sandbox_bash tool — persistent shell sessions in Docker sandbox.

This tool is Docker-only. On native backends (Seatbelt, Bubblewrap) the
agent should chain commands in a single ``sandbox_exec`` call instead.
"""

from __future__ import annotations

import logging
from typing import Any

from ..sandbox.manager import DockerSandbox
from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class SandboxBashTool(BaseTool):
    """Persistent bash sessions inside the sandbox container.

    Two modes:
    - **command** (default): Send a command, wait for output. Working dir and
      env vars persist across calls within the same session.
    - **raw I/O**: Use action="create"/"write"/"read" for interactive programs
      like top, vim, or long-running servers.
    """

    def __init__(self, sandbox: DockerSandbox) -> None:
        self._sandbox = sandbox

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="persistent_shell",
            description=(
                "Run commands in a persistent bash session. "
                "Working directory and environment variables persist across calls. "
                "Sessions are created implicitly on first use. "
                "For command-and-response mode, provide 'command'. "
                "For interactive programs, use action='create'/'write'/'read'."
            ),
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description=(
                        "Shell command to run (command-and-response mode). "
                        "Omit when using action-based raw I/O."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="session",
                    type="string",
                    description="Session name (default: 'default'). Sessions persist across calls.",
                    required=False,
                    default="default",
                ),
                ToolParameter(
                    name="action",
                    type="string",
                    description=(
                        "Raw I/O action: 'create' (create session), "
                        "'write' (send stdin), 'read' (poll output). "
                        "Omit for command-and-response mode."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="input",
                    type="string",
                    description="Data to write to stdin (only with action='write')",
                    required=False,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Max wait time in seconds for command mode (default: 120)",
                    required=False,
                    default=120,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        session: str = kwargs.get("session", "default")
        action: str | None = kwargs.get("action")
        command: str | None = kwargs.get("command")

        try:
            # Raw I/O mode
            if action is not None:
                return await self._handle_action(action, session, kwargs)

            # Command-and-response mode (default)
            if command is None:
                return {
                    "error": "Either 'command' or 'action' must be provided",
                    "message": "Please provide a command to run or an action (create/write/read).",
                }

            timeout: int = kwargs.get("timeout", 120)
            logger.info("sandbox_bash [%s]: %s", session, command)

            result = await self._sandbox.bash_command(
                command=command,
                session=session,
                timeout=timeout,
            )
            data = result.to_dict()
            data["message"] = result.output if result.output else "(no output)"
            return data

        except Exception as e:
            logger.error("sandbox_bash failed: %s", e, exc_info=True)
            return {"error": str(e), "message": f"Sandbox bash error: {e}"}

    async def _handle_action(
        self, action: str, session: str, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        if action == "create":
            await self._sandbox.ensure_container()
            await self._sandbox.bash_command(command="true", session=session, timeout=10)
            return {
                "session": session,
                "status": "created",
                "message": f"Session '{session}' created.",
            }

        if action == "write":
            data = kwargs.get("input", "")
            await self._sandbox.session_write(session, data)
            return {
                "session": session,
                "status": "written",
                "message": f"Sent {len(data)} bytes to session '{session}'.",
            }

        if action == "read":
            output = await self._sandbox.session_read(session)
            return {
                "session": session,
                "output": output,
                "message": output if output else "(no new output)",
            }

        return {
            "error": f"Unknown action: {action}",
            "message": f"Unknown action '{action}'. Use 'create', 'write', or 'read'.",
        }
