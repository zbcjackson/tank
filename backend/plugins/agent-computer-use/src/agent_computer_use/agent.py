"""Generic SubAgent lifecycle adapter; domain state stays in the controller."""

from collections.abc import AsyncIterator
from typing import Protocol

from tank_backend.agents.base import AgentOutput
from tank_backend.agents.subagent import (
    SubAgent,
    SubAgentCancelled,
    SubAgentCapabilities,
    SubAgentCleanupError,
    SubAgentContext,
    SubAgentRequest,
)

from .controller import ComputerUseController


class OwnedResource(Protocol):
    async def aclose(self) -> None: ...


class ComputerUseSubAgent(SubAgent):
    capabilities = SubAgentCapabilities(cancel=True)

    def __init__(
        self,
        controller: ComputerUseController,
        *,
        resources: tuple[OwnedResource, ...] = (),
    ) -> None:
        self.controller = controller
        self.resources = resources

    async def run(
        self,
        request: SubAgentRequest,
        context: SubAgentContext,
    ) -> AsyncIterator[AgentOutput]:
        try:
            result = await self.controller.run(request, context)
        except SubAgentCancelled as exc:
            # The generic adapter retains DONE evidence before joining cleanup on cancellation.
            if exc.task_result is not None:
                yield exc.task_result.to_output()
            raise
        yield result.to_output()

    async def aclose(self) -> None:
        failures: list[str] = []
        for resource in reversed(self.resources):
            try:
                await resource.aclose()
            except Exception as exc:
                failures.append(type(exc).__name__)
        if failures:
            raise SubAgentCleanupError("Owned resource cleanup failed: " + ", ".join(failures))
