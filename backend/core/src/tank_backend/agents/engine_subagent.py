"""Run a legacy Agent under the same task lifecycle as SubAgent plugins."""

from collections.abc import AsyncIterator
from uuid import uuid4

from .base import Agent, AgentOutput, AgentOutputType, AgentState
from .subagent import SubAgent, SubAgentContext, SubAgentRequest


class EngineSubAgent(SubAgent):
    def __init__(self, engine: Agent, state: AgentState) -> None:
        super().__init__()
        self.engine, self.state = engine, state

    async def run(
        self, request: SubAgentRequest, context: SubAgentContext,
    ) -> AsyncIterator[AgentOutput]:
        self.check_open()
        outputs = self.engine.run(self.state)
        try:
            async for output in outputs:
                if output.type == AgentOutputType.USAGE:
                    call_id = output.metadata.get("call_id") or uuid4().hex
                    context.budget.record_event(call_id, output.metadata)
                    context.check()
                if output.type == AgentOutputType.DONE:
                    output = AgentOutput(output.type, output.content, {
                        "stop_reason": "final_answer", **output.metadata,
                    })
                yield output
        finally:
            close = getattr(outputs, "aclose", None)
            if close is not None:
                await close()
