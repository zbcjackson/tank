"""ConfirmActionTool — executes or rejects a parked tool call."""

import json
import logging
from typing import Any

from .base import BaseTool, ToolInfo, ToolMetadata, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class ConfirmActionTool(BaseTool):
    """Executes or rejects the oldest pending tool call.

    Only available in CONFIRMING mode (tool_filter=["confirm_action"]).
    Bypasses ApprovalGateExecutor — calls ToolManager directly.
    """

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(idempotent=False)

    def __init__(
        self,
        pending_store: Any,       # PendingToolCallStore
        tool_manager: Any,        # ToolManager
        approval_policy: Any,     # ToolApprovalPolicy
    ) -> None:
        self._store = pending_store
        self._tool_manager = tool_manager
        self._policy = approval_policy

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="confirm_action",
            description=(
                "Approve or reject the pending tool action. "
                "Call with approved=true to execute, approved=false to reject."
            ),
            parameters=[
                ToolParameter(
                    name="approved",
                    type="boolean",
                    description="true to approve and execute, false to reject",
                    required=True,
                ),
            ],
        )

    async def execute(self, approved: bool, **kwargs: Any) -> ToolResult:
        pending = self._store.get_oldest_pending()
        if pending is None:
            return ToolResult(
                content=json.dumps({"error": "No pending action to confirm"}),
                display="No pending action",
                error=True,
            )

        consumed = self._store.consume(pending.approval_id)
        if consumed is None:
            return ToolResult(
                content=json.dumps({"error": "Pending action was already consumed"}),
                display="Action already resolved",
                error=True,
            )

        if not approved:
            return ToolResult(
                content=json.dumps({
                    "status": "rejected",
                    "tool_name": consumed.tool_name,
                    "description": consumed.description,
                }),
                display=f"Rejected: {consumed.description}",
            )

        # Approved — execute the tool directly via ToolManager
        result = await self._tool_manager.execute_tool(
            consumed.tool_name, **consumed.tool_args,
        )

        # Normalize result
        if isinstance(result, ToolResult):
            return result
        if isinstance(result, dict) and "error" in result:
            return ToolResult(
                content=json.dumps(result, ensure_ascii=False),
                display=f"Error: {result['error']}",
                error=True,
            )
        return ToolResult(
            content=(
                json.dumps(result, ensure_ascii=False)
                if isinstance(result, dict)
                else str(result)
            ),
            display=f"Executed: {consumed.description}",
        )
