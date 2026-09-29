"""Generic SubAgent lifecycle adapter; domain state stays in the controller."""

from collections.abc import AsyncIterator
from typing import Protocol

from tank_backend.agents.base import AgentOutput
from tank_backend.agents.subagent import (
    SubAgent,
    SubAgentCancelled,
    SubAgentCapabilities,
    SubAgentContext,
    SubAgentRequest,
)
from tank_backend.agents.task_resources import TaskResources
from tank_backend.agents.task_runtime import TaskRuntime

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
        self.resources = TaskResources(timeout=2.0)
        for index, resource in enumerate(resources):
            self.resources.own(str(index), resource.aclose)
        self.runtime: TaskRuntime | None = None

    async def run(
        self,
        request: SubAgentRequest,
        context: SubAgentContext,
    ) -> AsyncIterator[AgentOutput]:
        if self.runtime is not None:
            raise RuntimeError("A computer-use plugin cannot restart a task")
        self.runtime = context.runtime
        self.runtime.own("computer_use_channels", self.resources.aclose)
        try:
            result = await self.controller.run(request, context)
        except SubAgentCancelled as exc:
            # The generic adapter retains DONE evidence before joining cleanup on cancellation.
            if exc.task_result is not None:
                yield exc.task_result.to_output()
            raise
        yield result.to_output()

    async def aclose(self) -> None:
        if self.runtime is not None:
            await self.runtime.aclose()
        else:
            await self.resources.aclose()
