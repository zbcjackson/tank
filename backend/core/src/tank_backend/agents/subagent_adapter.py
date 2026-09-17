"""Expose a public SubAgent through the existing AgentRunner output path."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .base import Agent, AgentOutput, AgentOutputType, AgentState
from .subagent import (
    SubAgent,
    SubAgentCleanupError,
    SubAgentContext,
    SubAgentRequest,
    SubAgentStopped,
)

CLEANUP_TIMEOUT_S = 10.0


class SubAgentAdapter(Agent):
    def __init__(
        self, name: str, plugin: SubAgent, request: SubAgentRequest, context: SubAgentContext
    ) -> None:
        super().__init__(name)
        self.plugin = plugin
        self.request = request
        self.context = context

    async def run(self, state: AgentState) -> AsyncIterator[AgentOutput]:
        terminal: AgentOutput | None = None
        outputs = self.plugin.run(self.request, self.context)
        try:
            async for output in outputs:
                if terminal is not None:
                    raise SubAgentStopped("error", "events after DONE")
                if output.type == AgentOutputType.DONE:
                    terminal = output
                else:
                    yield output
        finally:
            # Cleanup errors override success/cancel/timeout. Do not swallow an
            # uncertain desktop cleanup and let the next task use the resource.
            try:

                async def close() -> None:
                    try:
                        close_outputs = getattr(outputs, "aclose", None)
                        if close_outputs is not None:
                            await close_outputs()
                    finally:
                        await self.plugin.aclose()

                await asyncio.wait_for(close(), CLEANUP_TIMEOUT_S)
            except Exception as exc:
                raise SubAgentCleanupError(f"subagent cleanup unconfirmed: {exc}") from exc
        if terminal is None:
            raise SubAgentStopped("error", "plugin ended without DONE")
        reason = terminal.metadata.get("stop_reason")
        if reason == "timeout":
            raise TimeoutError("subagent timeout")
        if reason != "final_answer":
            raise SubAgentStopped(
                str(reason or "error"),
                "plugin did not finish the task",
                terminal.metadata,
            )
        yield AgentOutput(
            AgentOutputType.DONE,
            terminal.content,
            {
                **terminal.metadata,
                "total_tokens": self.context.budget.total_tokens,
                "unknown_calls": len(self.context.budget.unknown_calls),
                "cleanup": "confirmed",
            },
        )
