"""AgentTool — the ``agent`` tool for spawning sub-agents."""

from __future__ import annotations

import logging
from typing import Any

from ..tools.base import BaseTool, ToolInfo, ToolParameter
from .base import AgentOutputType
from .runner import AgentRunner

logger = logging.getLogger(__name__)


class AgentTool(BaseTool):
    """Spawn a sub-agent to handle a complex task.

    The LLM calls this tool with a task description and an optional
    agent type.  The tool delegates to ``AgentRunner.run_agent()``
    which creates a ``ChatAgent`` with the agent definition's system
    prompt and tool constraints, runs it to completion, and returns
    the result.
    """

    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner

    def get_info(self) -> ToolInfo:
        # Build description with available agent types
        defs = self._runner.definitions
        agent_list = ", ".join(
            f"'{name}'" for name in sorted(defs)
        ) if defs else "none configured"

        return ToolInfo(
            name="agent",
            description=(
                "Launch a sub-agent to handle a complex task autonomously. "
                "The agent gets its own conversation context and tools. "
                f"Available types: {agent_list}."
            ),
            parameters=[
                ToolParameter(
                    name="prompt",
                    type="string",
                    description="Clear, specific task description for the agent",
                    required=True,
                ),
                ToolParameter(
                    name="subagent_type",
                    type="string",
                    description=(
                        "Agent type to use (e.g. 'coder', 'researcher', "
                        "'tasker'). Defaults to 'coder'."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="Short description (3-5 words) for tracking",
                    required=False,
                ),
                ToolParameter(
                    name="run_in_background",
                    type="boolean",
                    description="Run in background for parallel execution",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        agent_type = kwargs.get("subagent_type", "coder")
        prompt: str = kwargs["prompt"]
        background = kwargs.get("run_in_background", False)
        description = kwargs.get("description", "")

        agent_def = self._runner.get_definition(agent_type)
        if agent_def is None:
            available = sorted(self._runner.definitions.keys())
            return {
                "error": f"Agent type '{agent_type}' not found",
                "message": (
                    f"Agent type '{agent_type}' not found. "
                    f"Available: {', '.join(available)}"
                ),
            }

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        full_text = ""
        tool_calls = 0

        async for output in self._runner.run_agent(
            agent_def=agent_def,
            messages=messages,
            background=background or agent_def.background,
        ):
            if output.type == AgentOutputType.TOKEN:
                full_text += output.content
            elif output.type in (
                AgentOutputType.TOOL_EXECUTING,
                AgentOutputType.TOOL_RESULT,
            ):
                tool_calls += 1

        logger.info(
            "AgentTool: '%s' completed (%d chars, %d tool events)",
            agent_type, len(full_text), tool_calls,
        )

        return {
            "agent_type": agent_type,
            "description": description,
            "message": full_text or f"Agent '{agent_type}' completed (no text output).",
        }
