"""Explicit plugin assembly; construction never starts browser or model work."""

import json
from uuid import uuid4

from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped

from .agent import ComputerUseSubAgent
from .contracts import Action, Binding, DispatchReceipt, Snapshot
from .controller import ComputerUseController, Selector


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
        if (set(config) - {"browser", "macos", "selector", "advisor"}
                or len(set(config) & {"browser", "macos"}) != 1
                or ("selector" in config and config["selector"] not in ("jev", "llm", "jev-fallback"))
                or ("advisor" in config and config["advisor"] != "llm")):
            raise ValueError("Specify one explicit browser or macos channel")
        from .channels.native import NativeAXChannel, NativeConfig

        completion_keys = None
        max_candidates = 32
        if "macos" in config:
            channel = NativeAXChannel(NativeConfig.model_validate_json(
                json.dumps(config["macos"], allow_nan=False)))
            completion_keys = channel.completion_keys
            max_candidates = 64
        else:
            from .channels.dom import BrowserConfig, ManagedChromiumChannel

            channel = ManagedChromiumChannel(BrowserConfig.model_validate(config["browser"]))
        from .jev import JevSelector

        from .advisor import LLMAdvisor

        advisor = LLMAdvisor() if config.get("advisor") == "llm" else None
        selector: Selector | None = None
        if config.get("selector") == "jev":
            selector = JevSelector()
        elif config.get("selector") in ("llm", "jev-fallback"):
            from .model_selector import ModelSelector

            selector = ModelSelector(use_jev=config["selector"] == "jev-fallback")
        return ComputerUseSubAgent(
            ComputerUseController(channel, channel, selector=selector, advisor=advisor,
                                  completion_keys=completion_keys,
                                  max_candidates=max_candidates), resources=(channel,),
        )
    channel = UnavailableChannel()
    return ComputerUseSubAgent(ComputerUseController(channel, channel))
