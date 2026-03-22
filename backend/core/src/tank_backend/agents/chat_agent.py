"""ChatAgent — wraps existing LLM.chat_stream as an Agent."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..core.events import UpdateType
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
    ) -> None:
        super().__init__(name)
        self._llm = llm
        self._tool_manager = tool_manager
        self._system_prompt = system_prompt
        self._tool_filter = tool_filter

    def _get_tools(self) -> tuple[list[dict[str, Any]], Any]:
        """Return (openai_tools, tool_executor) respecting optional filter."""
        if self._tool_manager is None:
            return [], None
        tools = self._tool_manager.get_openai_tools()
        if self._tool_filter is not None:
            allowed = set(self._tool_filter)
            tools = [t for t in tools if t["function"]["name"] in allowed]
        return tools, self._tool_manager

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
                    if output.type in (
                        AgentOutputType.TOOL_CALLING,
                        AgentOutputType.TOOL_RESULT,
                    ):
                        tool_call_count += 1
                        if output.type == AgentOutputType.TOOL_CALLING:
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
