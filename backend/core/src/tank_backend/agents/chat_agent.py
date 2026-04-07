"""ChatAgent — wraps existing LLM.chat_stream as an Agent."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..core.events import UpdateType
from .approval import (
    ApprovalManager,
    ApprovalRequest,
    ToolApprovalPolicy,
    make_approval_id,
)
from .base import Agent, AgentOutput, AgentOutputType, AgentState

if TYPE_CHECKING:
    from ..llm.llm import LLM
    from ..tools.manager import ToolManager

logger = logging.getLogger(__name__)

# Maps UpdateType + TOOL status to AgentOutputType
_TOOL_STATUS_MAP: dict[str, AgentOutputType] = {
    "calling": AgentOutputType.TOOL_CALLING,
    "executing": AgentOutputType.TOOL_EXECUTING,
    "success": AgentOutputType.TOOL_RESULT,
    "error": AgentOutputType.TOOL_RESULT,
}


class _ApprovalToolExecutor:
    """Wraps a ToolManager to add approval gates before tool execution.

    When a tool requires approval, this executor awaits the approval Future
    before delegating to the real ToolManager. If rejected, returns a
    rejection message instead of executing.
    """

    def __init__(
        self,
        tool_manager: ToolManager,
        approval_manager: ApprovalManager,
        approval_policy: ToolApprovalPolicy,
        session_id: str,
    ) -> None:
        self._tool_manager = tool_manager
        self._approval_manager = approval_manager
        self._policy = approval_policy
        self._session_id = session_id
        # Pending approval request set by ChatAgent before the executor is called
        self._pending_request: ApprovalRequest | None = None

    async def execute_openai_tool_call(self, tool_call: Any) -> dict[str, Any]:
        """Execute a tool call, applying approval gate if needed."""
        tool_name = tool_call.function.name

        if self._pending_request is not None:
            request = self._pending_request
            self._pending_request = None  # Consume

            result = await self._approval_manager.request_approval(request)

            if not result.approved:
                reason = result.reason or "User declined"
                logger.info(
                    "Tool %s rejected: %s", tool_name, reason,
                )
                return {"error": f"Tool execution was declined by user: {reason}"}

            # Approved — record for first-time tracking
            self._policy.record_approved(tool_name)
            logger.info("Tool %s approved, executing", tool_name)

        return await self._tool_manager.execute_openai_tool_call(tool_call)


class ChatAgent(Agent):
    """Default conversational agent — delegates to LLM.chat_stream().

    Translates the ``(UpdateType, content, metadata)`` tuples from
    ``LLM.chat_stream()`` into ``AgentOutput`` items.
    """

    def __init__(
        self,
        name: str,
        llm: LLM,
        tool_manager: ToolManager | None = None,
        system_prompt: str | None = None,
        tool_filter: list[str] | None = None,
        approval_manager: ApprovalManager | None = None,
        approval_policy: ToolApprovalPolicy | None = None,
        session_id: str = "",
        exclude_tools: set[str] | None = None,
    ) -> None:
        super().__init__(name)
        self._llm = llm
        self._tool_manager = tool_manager
        self._system_prompt = system_prompt
        self._tool_filter = tool_filter
        self._approval_manager = approval_manager
        self._approval_policy = approval_policy
        self._session_id = session_id
        self._exclude_tools: set[str] = exclude_tools or set()

    def _get_tools(self) -> tuple[list[dict[str, Any]], Any]:
        """Return (openai_tools, tool_executor) with filter, exclusion, and approval."""
        if self._tool_manager is None:
            return [], None

        tools = self._tool_manager.get_openai_tools(exclude=self._exclude_tools or None)

        # Apply explicit allowlist filter if present
        if self._tool_filter is not None:
            allowed = set(self._tool_filter)
            tools = [t for t in tools if t["function"]["name"] in allowed]

        executor: Any = self._tool_manager
        has_approval = (
            self._approval_manager is not None
            and self._approval_policy is not None
        )
        if has_approval:
            executor = _ApprovalToolExecutor(
                tool_manager=self._tool_manager,
                approval_manager=self._approval_manager,
                approval_policy=self._approval_policy,
                session_id=self._session_id,
            )

        return tools, executor

    async def run(self, state: AgentState) -> AsyncIterator[AgentOutput]:
        """Stream LLM responses, translating to AgentOutput."""
        messages = list(state.messages)

        # Prepend agent-specific system prompt if configured
        if self._system_prompt:
            messages = [{"role": "system", "content": self._system_prompt}] + messages

        tools, executor = self._get_tools()
        tool_names = [t["function"]["name"] for t in tools] if tools else []
        logger.info(
            "Agent[%s] starting: %d messages, tools=%s",
            self.name, len(messages), tool_names or "none",
        )

        start = time.monotonic()
        full_text = ""
        tool_call_count = 0

        gen = self._llm.chat_stream(
            messages=messages,
            tools=tools or None,
            tool_executor=executor,
        )
        try:
            async for update_type, content, metadata in gen:
                output = _translate(update_type, content, metadata)
                if output is not None:
                    # Approval gate: intercept "executing" status for tools needing approval
                    if (
                        output.type == AgentOutputType.TOOL_EXECUTING
                        and self._approval_policy is not None
                        and self._approval_manager is not None
                        and self._approval_policy.needs_approval(metadata.get("name", ""))
                    ):
                        tool_name = metadata.get("name", "")
                        tool_args = _parse_tool_args(metadata.get("arguments", "{}"))
                        description = _build_tool_description(tool_name, tool_args)
                        approval_id = make_approval_id()

                        request = ApprovalRequest(
                            approval_id=approval_id,
                            tool_name=tool_name,
                            tool_args=tool_args,
                            description=description,
                            session_id=self._session_id,
                        )

                        # Set the pending request on the executor so it awaits it
                        if isinstance(executor, _ApprovalToolExecutor):
                            executor._pending_request = request

                        # Yield APPROVAL_NEEDED to the graph/brain
                        yield AgentOutput(
                            type=AgentOutputType.APPROVAL_NEEDED,
                            content=description,
                            metadata={
                                "approval_id": approval_id,
                                "tool_name": tool_name,
                                "tool_args": tool_args,
                                "description": description,
                                **metadata,
                            },
                        )
                        # Don't yield the TOOL_EXECUTING output — the approval
                        # gate replaces it. Execution continues on next iteration
                        # when chat_stream resumes and calls the executor.
                        continue

                    if output.type in (
                        AgentOutputType.TOOL_CALLING,
                        AgentOutputType.TOOL_EXECUTING,
                        AgentOutputType.TOOL_RESULT,
                    ):
                        tool_call_count += 1
                        if output.type == AgentOutputType.TOOL_EXECUTING:
                            logger.info(
                                "Agent[%s] tool call: %s(%s)",
                                self.name,
                                metadata.get("name", "?"),
                                metadata.get("arguments", "")[:80],
                            )
                        elif metadata.get("status") in ("success", "error"):
                            logger.info(
                                "Agent[%s] tool %s: %s → %s",
                                self.name,
                                metadata.get("status"),
                                metadata.get("name", "?"),
                                content[:120] if content else "",
                            )
                    yield output
                if update_type == UpdateType.TEXT:
                    full_text += content
        finally:
            await gen.aclose()

        elapsed = time.monotonic() - start

        # Append assistant response to shared state so downstream agents see it
        if full_text:
            state.messages.append({"role": "assistant", "content": full_text})

        logger.info(
            "Agent[%s] finished: %.3fs, %d chars, %d tool events",
            self.name, elapsed, len(full_text), tool_call_count,
        )

        yield AgentOutput(type=AgentOutputType.DONE)


def _translate(
    update_type: UpdateType,
    content: str,
    metadata: dict[str, Any],
) -> AgentOutput | None:
    """Translate a single LLM stream event to an AgentOutput."""
    if update_type == UpdateType.TEXT:
        return AgentOutput(type=AgentOutputType.TOKEN, content=content, metadata=metadata)

    if update_type == UpdateType.THOUGHT:
        return AgentOutput(type=AgentOutputType.THOUGHT, content=content, metadata=metadata)

    if update_type == UpdateType.TOOL:
        status = metadata.get("status", "calling")
        agent_type = _TOOL_STATUS_MAP.get(status, AgentOutputType.TOOL_CALLING)
        return AgentOutput(type=agent_type, content=content, metadata=metadata)

    return None


def _parse_tool_args(args_str: str) -> dict[str, Any]:
    """Parse tool arguments from JSON string, returning empty dict on failure."""
    if isinstance(args_str, dict):
        return args_str
    try:
        return json.loads(args_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def _build_tool_description(tool_name: str, tool_args: dict[str, Any]) -> str:
    """Build a human-readable description of a tool call."""
    if tool_name == "run_command" and "command" in tool_args:
        cmd = tool_args["command"]
        preview = cmd[:100] + "..." if len(cmd) > 100 else cmd
        return f"Run command: {preview}"
    if tool_name == "persistent_shell" and "command" in tool_args:
        cmd = tool_args["command"]
        preview = cmd[:100] + "..." if len(cmd) > 100 else cmd
        return f"Run in shell: {preview}"
    if tool_name == "manage_process":
        action = tool_args.get("action", "")
        pid = tool_args.get("process_id", "")
        return f"Process {action}: {pid}" if pid else f"Process {action}"
    # Generic fallback
    args_preview = str(tool_args)[:80]
    return f"Execute {tool_name}({args_preview})"
