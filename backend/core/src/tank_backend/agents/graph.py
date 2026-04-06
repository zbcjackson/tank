"""AgentGraph — orchestrates agent execution loop."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

from .base import Agent, AgentOutput, AgentOutputType, AgentState

logger = logging.getLogger(__name__)

MAX_GRAPH_ITERATIONS = 5


class AgentGraph:
    """Simple loop orchestrator: resolves default agent → agent runs → streams outputs.

    All TOKEN/THOUGHT/TOOL outputs stream through immediately.
    HANDOFF triggers resolution of the next agent.
    DONE terminates the loop.
    """

    def __init__(
        self,
        agents: dict[str, Agent],
        default_agent: str = "chat",
        max_iterations: int = MAX_GRAPH_ITERATIONS,
    ) -> None:
        self._agents = agents
        self._default_agent = default_agent
        self._max_iterations = max_iterations

    async def run(self, state: AgentState) -> AsyncIterator[AgentOutput]:
        """Execute the agent graph, streaming all outputs."""
        graph_start = time.monotonic()

        if self._default_agent not in self._agents:
            logger.error(
                "Default agent %r not found in %s",
                self._default_agent, list(self._agents.keys()),
            )
            return

        current_agent: Agent = self._agents[self._default_agent]

        for iteration in range(1, self._max_iterations + 1):
            state.agent_history.append(current_agent.name)
            state.turn = iteration

            agent_start = time.monotonic()
            token_count = 0
            tool_calls = 0
            agent_name = current_agent.name

            logger.info(
                "AgentGraph [iter %d] starting agent=%s", iteration, agent_name
            )

            async for output in current_agent.run(state):
                if output.type == AgentOutputType.HANDOFF:
                    target = output.target_agent
                    elapsed = time.monotonic() - agent_start
                    logger.info(
                        "AgentGraph [iter %d] agent=%s handoff → %s (%.3fs)",
                        iteration, agent_name, target, elapsed,
                    )
                    if target is None:
                        logger.warning("HANDOFF with no target_agent — stopping")
                        return
                    if target not in self._agents:
                        logger.error(
                            "HANDOFF to unknown agent %r — available: %s",
                            target, list(self._agents.keys()),
                        )
                        return
                    current_agent = self._agents[target]
                    break

                if output.type == AgentOutputType.DONE:
                    elapsed = time.monotonic() - agent_start
                    total = time.monotonic() - graph_start
                    logger.info(
                        "AgentGraph [iter %d] agent=%s done "
                        "(%.3fs, %d tokens, %d tool calls, total=%.3fs)",
                        iteration, agent_name, elapsed,
                        token_count, tool_calls, total,
                    )
                    return

                # Track stats for logging
                if output.type == AgentOutputType.TOKEN:
                    token_count += 1
                elif output.type in (
                    AgentOutputType.TOOL_CALLING,
                    AgentOutputType.TOOL_RESULT,
                ):
                    tool_calls += 1

                # Stream everything else through (TOKEN, THOUGHT, TOOL_*, APPROVAL_NEEDED)
                yield output
            else:
                # Agent completed without HANDOFF or DONE
                elapsed = time.monotonic() - agent_start
                total = time.monotonic() - graph_start
                logger.info(
                    "AgentGraph [iter %d] agent=%s completed implicitly "
                    "(%.3fs, %d tokens, %d tool calls, total=%.3fs)",
                    iteration, agent_name, elapsed,
                    token_count, tool_calls, total,
                )
                return

        # Max iterations exceeded
        total = time.monotonic() - graph_start
        logger.warning(
            "AgentGraph hit max iterations (%d) after %.3fs — stopping",
            self._max_iterations, total,
        )
