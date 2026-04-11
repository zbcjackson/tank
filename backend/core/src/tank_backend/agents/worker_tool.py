"""WorkerTool — wraps a ChatAgent as a callable tool for orchestrator agents."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from ..tools.base import BaseTool, ToolInfo, ToolParameter
from .base import AgentOutputType, AgentState

if TYPE_CHECKING:
    from .llm_agent import LLMAgent as ChatAgent

logger = logging.getLogger(__name__)


class WorkerTool(BaseTool):
    """A tool that delegates to an inner ChatAgent with focused tools.

    From the orchestrator's perspective, this is just another tool.
    The LLM calls it with a task description and gets back a structured result.

    The inner ChatAgent runs to completion — its tokens are NOT streamed
    to the user. The orchestrator synthesizes a user-facing response from
    the worker's output.

    Approval notifications are handled by the ApprovalManager's on_request
    callback (registered by the Brain), so they go through the same
    Bus/WebSocket path as all other UI messages.
    """

    def __init__(
        self,
        name: str,
        description: str,
        worker_agent: ChatAgent,
        timeout: float = 120.0,
    ) -> None:
        self._name = name
        self._description = description
        self._worker_agent = worker_agent
        self._timeout = timeout

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description=self._description,
            parameters=[
                ToolParameter(
                    name="task",
                    type="string",
                    description="Clear, specific description of the task to delegate",
                    required=True,
                ),
            ],
        )

    async def execute(self, task: str, **kwargs: Any) -> Any:
        """Run the inner agent on the given task and return a structured result."""
        state = AgentState(
            messages=[{"role": "user", "content": task}],
        )

        full_text = ""
        tools_used: list[str] = []

        try:
            async with asyncio.timeout(self._timeout):
                async for output in self._worker_agent.run(state):
                    if output.type == AgentOutputType.TOKEN:
                        full_text += output.content
                    elif output.type == AgentOutputType.TOOL_RESULT:
                        name = output.metadata.get("name", "unknown")
                        status = output.metadata.get("status", "unknown")
                        tools_used.append(f"{name}: {status}")
                    elif output.type == AgentOutputType.DONE:
                        break
        except TimeoutError:
            logger.warning(
                "Worker %s timed out after %.0fs (task: %s)",
                self._name, self._timeout, task[:80],
            )
            result: dict[str, Any] = {
                "status": "timeout",
                "message": f"Worker timed out after {self._timeout:.0f}s",
            }
            if full_text:
                result["partial_response"] = full_text
            return json.dumps(result)
        except Exception as e:
            logger.error("Worker %s error: %s", self._name, e, exc_info=True)
            result = {
                "status": "error",
                "message": f"Worker error: {e}",
            }
            if full_text:
                result["partial_response"] = full_text
            return json.dumps(result)

        result = {"status": "success", "response": full_text}
        if tools_used:
            result["tools_used"] = tools_used
        return json.dumps(result)
