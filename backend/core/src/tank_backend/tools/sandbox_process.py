"""sandbox_process tool — manage background processes across all backends."""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool, ToolInfo, ToolParameter

logger = logging.getLogger(__name__)


class SandboxProcessTool(BaseTool):
    """Manage sandbox background processes: list, poll, log, kill.

    Works on all backends (Docker, Seatbelt, Bubblewrap) via the Sandbox
    protocol's process management methods.
    """

    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="sandbox_process",
            description=(
                "Manage sandbox background processes started with sandbox_exec(background=true). "
                "Actions: "
                "'list' (all background processes), "
                "'poll' (recent output since last poll), "
                "'log' (full output history), "
                "'kill' (terminate process)."
            ),
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action: list, poll, log, kill",
                    required=True,
                ),
                ToolParameter(
                    name="process_id",
                    type="string",
                    description="Process ID (required for poll, log, kill)",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        action: str = kwargs["action"]
        process_id: str | None = kwargs.get("process_id")

        try:
            if action == "list":
                return self._handle_list()

            if process_id is None:
                return {
                    "error": "process_id required for this action",
                    "message": "Please provide a 'process_id'.",
                }

            handler = {
                "poll": self._handle_poll,
                "log": self._handle_log,
                "kill": self._handle_kill,
            }.get(action)

            if handler is None:
                return {
                    "error": f"Unknown action: {action}",
                    "message": (
                        f"Unknown action '{action}'. "
                        "Use: list, poll, log, kill."
                    ),
                }

            return await handler(process_id)

        except Exception as e:
            logger.error("sandbox_process failed: %s", e, exc_info=True)
            return {"error": str(e), "message": f"Sandbox process error: {e}"}

    def _handle_list(self) -> dict[str, Any]:
        processes = self._sandbox.list_processes()
        if not processes:
            return {"processes": [], "message": "No background processes."}
        lines = [
            f"  {p['process_id']}: {p['status']} — {p['command'][:60]}"
            for p in processes
        ]
        return {
            "processes": processes,
            "message": "Background processes:\n" + "\n".join(lines),
        }

    async def _handle_poll(self, process_id: str) -> dict[str, Any]:
        result = await self._sandbox.poll_process(process_id)
        data = result.to_dict()
        data["process_id"] = process_id
        data["message"] = result.output if result.output else "(no new output)"
        return data

    async def _handle_log(self, process_id: str) -> dict[str, Any]:
        output = await self._sandbox.process_log(process_id)
        return {
            "process_id": process_id,
            "output": output,
            "message": output if output else "(no output history)",
        }

    async def _handle_kill(self, process_id: str) -> dict[str, Any]:
        await self._sandbox.kill_process(process_id)
        return {
            "process_id": process_id,
            "status": "killed",
            "message": f"Process '{process_id}' terminated.",
        }
