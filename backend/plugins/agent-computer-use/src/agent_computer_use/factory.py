"""Offline S0 factory: real channel/model wiring is deliberately not advertised."""

from uuid import uuid4

from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped

from .agent import ComputerUseSubAgent
from .contracts import Action, Binding, DispatchReceipt, Snapshot
from .controller import ComputerUseController


class UnavailableChannel:
    async def observe(self, scope: str, context: SubAgentContext) -> Snapshot:
        return Snapshot(uuid4().hex, scope, 0, ready=False)

    async def is_current(self, binding: Binding, action: Action, context: SubAgentContext) -> bool:
        return False

    async def dispatch(
        self,
        binding: Binding,
        action: Action,
        context: SubAgentContext,
    ) -> DispatchReceipt:
        raise SubAgentStopped("channel_unavailable")


def create_subagent(config: dict[str, object]) -> ComputerUseSubAgent:
    if config:
        raise ValueError("S0 computer-use has no configurable live channels or providers yet")
    channel = UnavailableChannel()
    return ComputerUseSubAgent(ComputerUseController(channel, channel))
