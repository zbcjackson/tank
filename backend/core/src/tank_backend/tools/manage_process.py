"""manage_process tool — manage background processes."""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class ManageProcessTool(BaseTool):
    """Manage background processes: list, poll, log, kill."""

    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="manage_process",
            description=(
                "Manage background processes started with run_command(background=true). "
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

    async def execute(self, **kwargs: Any) -> ToolResult:
        action: str = kwargs["action"]
        process_id: str | None = kwargs.get("process_id")

        try:
            if action == "list":
                return self._handle_list()

            if process_id is None:
                return ToolResult(
                    content=json.dumps(
                        {"error": "process_id required for this action"},
                        ensure_ascii=False,
                    ),
                    display="Please provide a 'process_id'.",
                    error=True,
                )

            handler = {
                "poll": self._handle_poll,
                "log": self._handle_log,
                "kill": self._handle_kill,
            }.get(action)

            if handler is None:
                return ToolResult(
                    content=json.dumps(
                        {"error": f"Unknown action: {action}"},
                        ensure_ascii=False,
                    ),
                    display=(
                        f"Unknown action '{action}'. "
                        "Use: list, poll, log, kill."
                    ),
                    error=True,
                )

            return await handler(process_id)

        except Exception as e:
            logger.error("manage_process failed: %s", e, exc_info=True)
            return ToolResult(
                content=json.dumps({"error": str(e)}, ensure_ascii=False),
                display=f"Sandbox process error: {e}",
                error=True,
            )

    def _handle_list(self) -> ToolResult:
        processes = self._sandbox.list_processes()
        if not processes:
            return ToolResult(
                content=json.dumps({"processes": []}, ensure_ascii=False),
                display="No background processes.",
            )
        lines = [
            f"  {p['process_id']}: {p['status']} — {p['command'][:60]}"
            for p in processes
        ]
        return ToolResult(
            content=json.dumps({"processes": processes}, ensure_ascii=False),
            display="Background processes:\n" + "\n".join(lines),
        )

    async def _handle_poll(self, process_id: str) -> ToolResult:
        result = await self._sandbox.poll_process(process_id)
        data = result.to_dict()
        data["process_id"] = process_id
        display = result.output if result.output else "(no new output)"
        return ToolResult(
            content=json.dumps(data, ensure_ascii=False),
            display=display,
        )

    async def _handle_log(self, process_id: str) -> ToolResult:
        output = await self._sandbox.process_log(process_id)
        data = {"process_id": process_id, "output": output}
        display = output if output else "(no output history)"
        return ToolResult(
            content=json.dumps(data, ensure_ascii=False),
            display=display,
        )

    async def _handle_kill(self, process_id: str) -> ToolResult:
        await self._sandbox.kill_process(process_id)
        data = {"process_id": process_id, "status": "killed"}
        return ToolResult(
            content=json.dumps(data, ensure_ascii=False),
            display=f"Process '{process_id}' terminated.",
        )
