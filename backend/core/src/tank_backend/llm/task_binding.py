"""Bind an existing LLM to task governance without closing its host-owned HTTP pool."""

from __future__ import annotations

from uuid import uuid4

import httpx

from ..agents.subagent import SubAgentContext
from .llm import LLM
from .model_transport import ChatCompletionsRoute, TaskModelTransport
from .task_client import TaskOpenAI


class _BorrowedHTTP(httpx.AsyncBaseTransport):
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Preserve the host pool/proxy/test transport, not its legacy per-call hooks.
        return await self.client._transport_for_url(request.url).handle_async_request(request)

    async def aclose(self) -> None:
        pass


def bind_llm(llm: LLM, context: SubAgentContext, task_id: str) -> LLM:
    if llm.manages_task_usage:
        if llm._task_context is not context:
            raise ValueError("LLM belongs to another task runtime")
        return llm
    context.check("network")
    route = ChatCompletionsRoute(
        llm.base_url.rstrip("/") + "/chat/completions", llm.model, "llm",
        max_output_tokens=llm.max_tokens, max_upload_bytes=9_500_000,
        allow_images=True, allow_tools=True, allow_stream=True,
        allow_http=llm.base_url.startswith("http://"), extra_parameters=llm.extra_body,
    )
    transport = TaskModelTransport(
        task_id, context, routes=(route,), credentials={"llm": llm.api_key},
        inner=_BorrowedHTTP(llm.client._client),
    )
    client = TaskOpenAI(
        api_key="host-managed", base_url=llm.base_url, max_retries=0,
        default_headers=llm.extra_headers,
        http_client=httpx.AsyncClient(transport=transport, follow_redirects=False),
    )
    bound = LLM(
        api_key="host-managed", model=llm.model, base_url=llm.base_url,
        temperature=llm.temperature, max_tokens=llm.max_tokens,
        stream_options=llm.stream_options, extra_body=llm.extra_body, client=client,
    )
    bound._task_context = context
    bound._owns_client = True
    bound._retries_enabled = llm._retries_enabled
    context.runtime.own("llm-" + uuid4().hex, bound.aclose)
    return bound
