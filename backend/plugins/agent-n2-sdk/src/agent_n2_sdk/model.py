"""Pinned Yutori formatting over Tank's task-owned HTTP governance."""

from __future__ import annotations

from typing import Any

import httpx
from tank_backend.llm.task_client import TaskOpenAI
from yutori._async.chat import AsyncChatCompletions

from tank_backend.agents.subagent import SubAgentContext
from tank_backend.llm.model_transport import (
    ChatCompletionsRoute, ModelCallRecord, TaskModelTransport, get_model_call,
)

from .config import N2SdkConfig


class N2ModelClient:
    def __init__(
        self, config: N2SdkConfig, context: SubAgentContext,
        *, inner: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        context.check("network")
        route = ChatCompletionsRoute(
            config.base_url.rstrip("/") + "/chat/completions", config.model, config.credential_ref or "n2",
            max_upload_bytes=9_500_000, allow_images=True, allow_tools=True,
            require_max_tokens=False,
            extra_parameters={"tool_set": config.tool_set, "reasoning_effort": config.reasoning_effort},
            extra_types={"prev_request_id": str, "yutori_logical_request_id": str,
                         "yutori_logical_attempt": int, "disable_tools": list, "json_schema": dict},
        )
        if context.runtime.model is not None:
            self.transport = context.runtime.model.create_transport(route, inner=inner)
        else:
            # Explicit low-level callers may provide a key; normal Runner factories receive refs.
            self.transport = TaskModelTransport(
                context.runtime.task_id, context, routes=(route,),
                credentials={route.credential_ref: config.api_key},
                inner=inner or httpx.AsyncHTTPTransport(),
            )
        self.client = TaskOpenAI(
            api_key="host-managed", base_url=config.base_url, max_retries=0,
            http_client=httpx.AsyncClient(transport=self.transport, follow_redirects=False),
        )
        self.completions = AsyncChatCompletions(self.client)

    @property
    def last_record(self) -> ModelCallRecord | None:
        return get_model_call(self.transport.snapshot()["task_id"])

    async def create(self, **kwargs: Any) -> Any:
        return await self.completions.create(**kwargs)

    async def aclose(self) -> None:
        await self.client.close()
