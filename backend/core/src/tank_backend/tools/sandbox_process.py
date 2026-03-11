"""sandbox_process tool — manage sandbox bash sessions."""

from __future__ import annotations

import logging
from typing import Any

from ..sandbox.manager import SandboxManager
from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class SandboxProcessTool(BaseTool):
    """Manage sandbox bash sessions: list, poll, log, write, kill, clear, remove."""

    def __init__(self, sandbox: SandboxManager) -> None:
        self._sandbox = sandbox

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="sandbox_process",
            description=(
                "Manage sandbox bash sessions. Actions: "
                "'list' (all sessions), "
                "'poll' (recent output since last poll), "
                "'log' (full output history), "
                "'write' (send stdin), "
                "'kill' (terminate session), "
                "'clear' (clear output buffer), "
                "'remove' (remove terminated session)."
            ),
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action: list, poll, log, write, kill, clear, remove",
                    required=True,
                ),
                ToolParameter(
                    name="session",
                    type="string",
                    description="Session name (required for all actions except 'list')",
                    required=False,
                ),
                ToolParameter(
                    name="input",
                    type="string",
                    description="Data to write to stdin (only with action='write')",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        action: str = kwargs["action"]
        session: str | None = kwargs.get("session")

        try:
            if action == "list":
                return self._handle_list()

            if session is None:
                return {
                    "error": "Session name required for this action",
                    "message": "Please provide a 'session' name.",
                }

            handler = {
                "poll": self._handle_poll,
                "log": self._handle_log,
                "write": self._handle_write,
                "kill": self._handle_kill,
                "clear": self._handle_clear,
                "remove": self._handle_remove,
            }.get(action)

            if handler is None:
                return {
                    "error": f"Unknown action: {action}",
                    "message": (
                        f"Unknown action '{action}'. "
                        "Use: list, poll, log, write, kill, clear, remove."
                    ),
                }

            return await handler(session, kwargs)

        except Exception as e:
            logger.error("sandbox_process failed: %s", e, exc_info=True)
            return {"error": str(e), "message": f"Sandbox process error: {e}"}

    def _handle_list(self) -> dict[str, Any]:
        sessions = self._sandbox.list_sessions()
        if not sessions:
            return {"sessions": [], "message": "No active sessions."}
        lines = [f"  {s['name']}: {s['status']} ({s['output_lines']} lines)" for s in sessions]
        return {
            "sessions": sessions,
            "message": "Active sessions:\n" + "\n".join(lines),
        }

    async def _handle_poll(self, session: str, _kwargs: dict) -> dict[str, Any]:
        output = await self._sandbox.session_poll(session)
        return {
            "session": session,
            "output": output,
            "message": output if output else "(no new output)",
        }

    async def _handle_log(self, session: str, _kwargs: dict) -> dict[str, Any]:
        output = await self._sandbox.session_log(session)
        return {
            "session": session,
            "output": output,
            "message": output if output else "(no output history)",
        }

    async def _handle_write(self, session: str, kwargs: dict) -> dict[str, Any]:
        data = kwargs.get("input", "")
        await self._sandbox.session_write(session, data)
        return {
            "session": session,
            "status": "written",
            "message": f"Sent {len(data)} bytes to session '{session}'.",
        }

    async def _handle_kill(self, session: str, _kwargs: dict) -> dict[str, Any]:
        await self._sandbox.session_kill(session)
        return {
            "session": session,
            "status": "killed",
            "message": f"Session '{session}' terminated.",
        }

    async def _handle_clear(self, session: str, _kwargs: dict) -> dict[str, Any]:
        self._sandbox.session_clear(session)
        return {
            "session": session,
            "status": "cleared",
            "message": f"Output buffer for session '{session}' cleared.",
        }

    async def _handle_remove(self, session: str, _kwargs: dict) -> dict[str, Any]:
        await self._sandbox.session_remove(session)
        return {
            "session": session,
            "status": "removed",
            "message": f"Session '{session}' removed.",
        }
