"""Expose a public SubAgent through the existing AgentRunner output path."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .base import Agent, AgentOutput, AgentOutputType, AgentState
from .subagent import (
    SubAgent,
    SubAgentCancelled,
    SubAgentCleanupError,
    SubAgentContext,
    SubAgentRequest,
    SubAgentStopped,
)
from .task_result import TaskResult

CLEANUP_TIMEOUT_S = 10.0


class SubAgentAdapter(Agent):
    def __init__(
        self, name: str, plugin: SubAgent, request: SubAgentRequest, context: SubAgentContext
    ) -> None:
        super().__init__(name)
        self.plugin = plugin
        self.request = request
        self.context = context
        self.context.runtime.bind(request.task_id)

    async def run(self, state: AgentState) -> AsyncIterator[AgentOutput]:
        terminal: AgentOutput | None = None
        result: TaskResult | None = None
        cancelled = False
        outputs: AsyncIterator[AgentOutput] | None = None
        try:
            outputs = self.plugin.run(self.request, self.context)
            async for output in outputs:
                self.context.runtime.record_output(output)
                if terminal is not None:
                    raise SubAgentStopped("error", "events after DONE")
                if output.type == AgentOutputType.DONE:
                    terminal = output
                    if "task_result" in output.metadata:
                        result = TaskResult.model_validate(output.metadata["task_result"])
                        if output.metadata.get("stop_reason") != result.status:
                            raise SubAgentStopped("error", "task result disagrees with stop_reason")
                else:
                    yield output
        except SubAgentStopped as exc:
            if exc.reason != "output_limit":
                raise
            result = TaskResult(
                status="partial", reason="output_limit",
                summary="Output limit reached; partial output was retained.",
            )
            terminal = result.to_output()
        except asyncio.CancelledError:
            cancelled = True
            self.context.cancel.set()
        except SubAgentCleanupError as exc:
            result = result or exc.task_result
            raise SubAgentCleanupError(str(exc), result) from exc
        finally:
            # Cleanup errors override success/cancel/timeout. Do not swallow an
            # uncertain desktop cleanup and let the next task use the resource.
            try:

                async def close() -> None:
                    self.context.runtime.begin_close()
                    try:
                        close_outputs = getattr(outputs, "aclose", None)
                        if close_outputs is not None:
                            await close_outputs()
                    finally:
                        try:
                            # Core owns task shutdown; plugin cleanup only releases its resources.
                            await self.context.runtime.aclose()
                        finally:
                            await self.plugin.aclose()

                cleanup = asyncio.create_task(asyncio.wait_for(close(), CLEANUP_TIMEOUT_S))
                while True:
                    try:
                        await asyncio.shield(cleanup)
                        break
                    except asyncio.CancelledError as exc:
                        if cleanup.cancelled():
                            raise SubAgentCleanupError(
                                "plugin cancelled its cleanup", result,
                            ) from exc
                        cancelled = True
                        self.context.cancel.set()
            except Exception as exc:
                if isinstance(exc, SubAgentCleanupError):
                    result = result or exc.task_result
                raise SubAgentCleanupError(
                    f"subagent cleanup unconfirmed: {exc}", result,
                ) from exc
        if self.context.runtime.has_unknown_effect:
            if result is None:
                result = TaskResult(
                    status="unknown", reason="effect_unknown",
                    summary="Task ended with an unconfirmed action effect.",
                    details={"calls": [
                        {"call_id": item.call_id, "operation": item.operation,
                         "status": item.status}
                        for item in self.context.runtime.records
                    ]},
                )
            elif result.status != "unknown":
                result = result.model_copy(update={
                    "status": "unknown", "reason": "effect_unknown",
                    "summary": "Unconfirmed action effect. " + result.summary,
                })
            terminal = result.to_output()
        if cancelled:
            if result is not None:
                result = result.with_cleanup("confirmed")
            raise SubAgentCancelled(result)
        if self.context.runtime.audit_failed:
            if result is not None:
                result = result.with_cleanup("confirmed").model_copy(update={
                    "status": "unknown", "reason": "audit_failed",
                })
            raise SubAgentStopped("audit_failed", task_result=result)
        if terminal is None:
            raise SubAgentStopped("error", "plugin ended without DONE")
        reason = terminal.metadata.get("stop_reason")
        if result is not None:
            result = result.with_cleanup("confirmed")
            terminal = AgentOutput(
                AgentOutputType.DONE, result.summary,
                {**terminal.metadata, "task_result": result.model_dump(mode="json")},
            )
        if reason == "timeout":
            raise TimeoutError("subagent timeout")
        if reason != "final_answer" and "task_result" not in terminal.metadata:
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
