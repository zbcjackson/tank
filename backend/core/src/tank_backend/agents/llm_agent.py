"""LLMAgent — runs an agent via LLM.chat_stream with tool calling."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any

from ..core.events import UpdateType
from .approval import (
    ApprovalGateExecutor,
    PendingToolCallStore,
    ToolApprovalPolicy,
)
from .base import Agent, AgentOutput, AgentOutputType, AgentState

if TYPE_CHECKING:
    from ..llm.llm import LLM
    from ..tools.manager import ToolManager

logger = logging.getLogger(__name__)

_ACLOSE_TIMEOUT_S = 2.0

# Maps UpdateType + TOOL status to AgentOutputType
_TOOL_STATUS_MAP: dict[str, AgentOutputType] = {
    "calling": AgentOutputType.TOOL_CALLING,
    "executing": AgentOutputType.TOOL_EXECUTING,
    "success": AgentOutputType.TOOL_RESULT,
    "error": AgentOutputType.TOOL_RESULT,
}


class LLMAgent(Agent):
    """Agent that delegates to LLM.chat_stream().

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
        approval_policy: ToolApprovalPolicy | None = None,
        resolver: Any = None,
        session_id: str = "",
        exclude_tools: set[str] | None = None,
        pending_store: PendingToolCallStore | None = None,
        bus: Any = None,
        current_msg_id_fn: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(name)
        self._llm = llm
        self._tool_manager = tool_manager
        self._system_prompt = system_prompt
        self._tool_filter = tool_filter
        self._approval_policy = approval_policy
        self._resolver = resolver
        self._session_id = session_id
        self._exclude_tools: set[str] = exclude_tools or set()
        self._pending_store = pending_store
        self._bus = bus
        self._current_msg_id_fn = current_msg_id_fn or (lambda: "")

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
        has_gate = (
            self._pending_store is not None
            and self._approval_policy is not None
            and self._bus is not None
        )
        if has_gate:
            # ``has_gate`` is derived from three non-None checks above;
            # pyright can't narrow through a cached boolean, so re-assert
            # the invariants at the seam.
            assert self._pending_store is not None  # noqa: S101
            assert self._approval_policy is not None  # noqa: S101
            assert self._bus is not None  # noqa: S101

            resolver = self._resolver
            if resolver is None:
                from .approval import InteractiveResolver
                resolver = InteractiveResolver(
                    pending_store=self._pending_store,
                    session_id=self._session_id,
                    bus=self._bus,
                    current_msg_id_fn=self._current_msg_id_fn,
                )
            executor = ApprovalGateExecutor(
                tool_manager=self._tool_manager,
                approval_policy=self._approval_policy,
                resolver=resolver,
                pending_store=self._pending_store,
                session_id=self._session_id,
                bus=self._bus,
                current_msg_id_fn=self._current_msg_id_fn,
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
        turn_messages: list[dict[str, Any]] = []

        # Extract system prompt refresher from state metadata
        system_prompt_fn = state.metadata.get("system_prompt_fn")

        gen = self._llm.chat_stream(
            messages=messages,  # type: ignore[arg-type]  # state.messages is broader than ChatCompletionMessageParam
            tools=tools or None,
            tool_executor=executor,
            trace_metadata={
                "trace_name": f"agent:{self.name}",
                "metadata": {"agent_name": self.name},
            },
            system_prompt_fn=system_prompt_fn,
            # Phase 18: thread MediaStore + session through so the
            # LLM loop can materialize ``media://`` URIs returned by
            # tools (e.g. ``render_chart``) into data URLs the LLM
            # provider accepts. ``getattr`` keeps narrow tests that
            # mock ``ToolManager`` without ``_media_store`` working.
            media_store=getattr(self._tool_manager, "_media_store", None),
            # Read the session id at call time from ``ToolManager``
            # (Phase 18 keeps it in sync via ``set_session_id``)
            # rather than from the agent's constructor — Brain builds
            # the agent before its ``_context`` is initialised, so
            # the constructor value is reliably empty here. Falling
            # back to ``self._session_id`` preserves existing test
            # paths that pass an explicit id at construction time.
            session_id=(
                getattr(self._tool_manager, "_session_id", None)
                or self._session_id
            ),
        )
        try:
            async for update_type, content, metadata in gen:
                if update_type == UpdateType.MESSAGE:
                    turn_messages.append(metadata["message"])
                    continue
                output = _translate(update_type, content, metadata)
                if output is not None:
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
            try:
                await asyncio.wait_for(gen.aclose(), timeout=_ACLOSE_TIMEOUT_S)
            except asyncio.TimeoutError:
                logger.warning(
                    "LLM stream aclose() timed out in Agent[%s]",
                    self.name,
                )

        elapsed = time.monotonic() - start

        # Store turn messages for Brain to persist
        state.metadata["turn_messages"] = turn_messages

        logger.info(
            "Agent[%s] finished: %.3fs, %d chars, %d tool events",
            self.name, elapsed, len(full_text), tool_call_count,
        )

        yield AgentOutput(type=AgentOutputType.DONE, metadata={"turn_messages": turn_messages})


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

    if update_type == UpdateType.USAGE:
        return AgentOutput(type=AgentOutputType.USAGE, content="", metadata=metadata)

    return None


def _parse_tool_args(args_str: str) -> dict[str, Any]:
    """Parse tool arguments from JSON string, returning empty dict on failure."""
    if isinstance(args_str, dict):
        return args_str
    try:
        return json.loads(args_str)
    except (json.JSONDecodeError, TypeError):
        return {}
