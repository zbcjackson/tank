"""Explicit plugin assembly; construction never starts browser or model work."""

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
        if set(config) != {"browser"} or not isinstance(config["browser"], dict):
            raise ValueError("Only an explicit browser configuration is supported")
        from .channels.dom import BrowserConfig, ManagedChromiumChannel

        browser = ManagedChromiumChannel(BrowserConfig.model_validate(config["browser"]))
        return ComputerUseSubAgent(ComputerUseController(browser, browser), resources=(browser,))
    channel = UnavailableChannel()
    return ComputerUseSubAgent(ComputerUseController(channel, channel))
