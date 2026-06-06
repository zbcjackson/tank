"""AskUserTool — sub-agent tool to pause and ask the user a question."""

from __future__ import annotations

from typing import Any

from ..tools.base import BaseTool, ToolInfo, ToolParameter, ToolResult


class AskUserTool(BaseTool):
    """Ask the user a question — pauses worker execution until answered."""

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="ask_user",
            description=(
                "Ask the user a question when you need clarification. "
                "Your execution pauses until they respond. Use when you "
                "have options to present or critical info is missing."
            ),
            parameters=[
                ToolParameter(
                    name="question",
                    type="string",
                    description="The question to ask the user",
                    required=True,
                ),
                ToolParameter(
                    name="options",
                    type="string",
                    description="Comma-separated list of choices (optional)",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        question = kwargs["question"]
        options = kwargs.get("options", "")
        display = question + (f" Options: {options}" if options else "")
        return ToolResult(content=display, display=display)
