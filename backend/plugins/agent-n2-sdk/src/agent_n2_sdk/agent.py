"""Run the official SDK; Tank does not implement its prediction/tool loop."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import replace
from typing import Any

from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.subagent import (
    SubAgent,
    SubAgentCapabilities,
    SubAgentCleanupError,
    SubAgentContext,
    SubAgentRequest,
    SubAgentStopped,
)
from yutori import AsyncYutoriClient
from yutori.navigator.n2 import N2ComputerAgent

from .callbacks import Callbacks, MeteredCompletions
from .config import N2SdkConfig
from .environment import create_computer


def create_client(config: N2SdkConfig) -> AsyncYutoriClient:
    return AsyncYutoriClient(api_key=config.api_key, base_url=config.base_url)


class N2SdkSubAgent(SubAgent):
    capabilities = SubAgentCapabilities(cancel=True)

    def __init__(
        self,
        config: N2SdkConfig,
        *,
        computer_factory: Callable[[SubAgentContext], Any] = create_computer,
        client_factory: Callable[[N2SdkConfig], Any] = create_client,
    ) -> None:
        self.config = config
        self.computer_factory, self.client_factory = computer_factory, client_factory
        self.computer: Any = None
        self.client: Any = None
        self.sdk: N2ComputerAgent | None = None
        self.producer: asyncio.Task[None] | None = None
        self.error: BaseException | None = None
        self.closing = False
        self.closed = False

    async def run(
        self, request: SubAgentRequest, context: SubAgentContext
    ) -> AsyncGenerator[AgentOutput, None]:
        if self.closed or self.producer is not None:
            raise RuntimeError("N2 SDK instance is single-use")
        deadline = min(
            context.deadline or float("inf"), time.monotonic() + self.config.timeout_s
        )
        context = replace(context, deadline=deadline)
        queue: asyncio.Queue[AgentOutput | None] = asyncio.Queue(maxsize=64)
        callbacks = Callbacks(queue, context)

        async def produce() -> None:
            try:
                context.check()
                self.computer = self.computer_factory(context)
                context.observe("sdk_start", sdk_version="0.9.29")
                await self.computer.__aenter__()
                context.check()
                self.client = self.client_factory(self.config)
                completions = (
                    self.client.chat.completions
                    if hasattr(self.client, "chat")
                    else self.client
                )
                metered = MeteredCompletions(completions, context, queue)
                callbacks.completions = metered
                self.sdk = N2ComputerAgent(
                    computer=self.computer,
                    completions=metered,
                    callbacks=[callbacks],
                    instructions=request.context or None,
                    model=self.config.model,
                    tool_set=self.config.tool_set,
                    reasoning_effort=self.config.reasoning_effort,
                    max_steps=self.config.max_steps,
                    screenshot_delay=self.config.screenshot_delay,
                    execution_deadline=deadline,
                    supports_click_modifiers=True,
                    supports_scroll_modifiers=False,
                )
                frames = self.sdk.run(request.task)
                try:
                    async for _frame in frames:
                        pass  # SDK callbacks are the single source of UI events.
                finally:
                    await frames.aclose()
                reason = self.sdk.stopped_by or "error"
            except SubAgentStopped as exc:
                reason = exc.reason
            except BaseException as exc:
                self.error = exc
                if self.closing:
                    return
                await queue.put(None)
                return
            await queue.put(
                AgentOutput(
                    AgentOutputType.DONE,
                    metadata={
                        "stop_reason": reason,
                        "sdk_version": "0.9.29",
                        "steps": callbacks.steps,
                        "primitives": callbacks.primitives,
                        "model_turns": callbacks.model_turns,
                    },
                )
            )
            await queue.put(None)

        async def watch_cancel() -> None:
            await context.cancel.wait()
            if self.computer is not None:
                self.computer.cancellation.request("user_stop")
            if self.producer is not None:
                self.producer.cancel()

        self.producer = asyncio.create_task(produce(), name=f"n2-sdk:{request.task_id}")
        cancellation = asyncio.create_task(watch_cancel())
        try:
            while True:
                output = await asyncio.wait_for(
                    queue.get(), max(0, deadline - time.monotonic())
                )
                if output is None:
                    if self.error is not None:
                        raise self.error
                    break
                yield output
        finally:
            cancellation.cancel()
            try:
                await cancellation
            except asyncio.CancelledError:
                pass
            await self.aclose()

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closing = True
        errors: list[str] = []
        if self.producer is not None and not self.producer.done():
            if self.computer is not None:
                self.computer.cancellation.request("user_stop")
            self.producer.cancel()

        async def cleanup() -> None:
            if self.producer is not None:
                try:
                    await self.producer
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    errors.append(str(exc))
            for resource in (self.sdk, self.computer, self.client):
                if resource is None:
                    continue
                try:
                    close = getattr(resource, "aclose", None) or getattr(
                        resource, "close"
                    )
                    await close()
                except Exception as exc:
                    errors.append(str(exc))

        try:
            await asyncio.wait_for(cleanup(), self.config.cleanup_timeout_s)
        except Exception as exc:
            errors.append(str(exc) or type(exc).__name__)
        self.closed = True
        if errors:
            raise SubAgentCleanupError(
                "N2 SDK cleanup unconfirmed: " + "; ".join(errors)
            )
