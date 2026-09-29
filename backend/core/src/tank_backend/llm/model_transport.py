"""Task-owned model HTTP admission. Protocol data never enters the shared ledger."""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from uuid import uuid4

import httpx

from ..agents.subagent import SubAgentContext
from ..core.spend_ledger import (
    SpendLedger,
    SpendLimit,
    SpendLimitExceeded,
    SpendSnapshot,
    TokenAllowance,
)


class ModelSnapshot(SpendSnapshot):
    task_id: str
    sent_requests: int


@dataclass(frozen=True)
class ChatCompletionsRoute:
    url: str
    model: str
    allowance: TokenAllowance
    credential_ref: str
    max_upload_bytes: int = 65536

    def __post_init__(self) -> None:
        url = httpx.URL(self.url)
        if (
            url.scheme != "https" or not url.host or url.userinfo or url.query or url.fragment
            or not self.model or not self.credential_ref
            or type(self.max_upload_bytes) is not int or self.max_upload_bytes <= 0
        ):
            raise ValueError("model route requires an exact HTTPS endpoint and bounded upload")

    def validate(self, request: httpx.Request) -> None:
        if request.method != "POST" or len(request.content) > self.max_upload_bytes:
            raise ValueError("model request method or upload size rejected")
        data = json_object(request.content)
        maximum = data.get("max_tokens")
        if (
            data.get("model") != self.model or data.get("stream", False) is not False
            or type(maximum) is not int or not 0 < maximum <= self.allowance.output_tokens
            or set(data) - {"model", "messages", "max_tokens", "stream", "temperature"}
        ):
            raise ValueError("model request outside approved protocol")
        temperature = data.get("temperature", 1)
        if (
            isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature) or not 0 <= temperature <= 2
        ):
            raise ValueError("model temperature is outside the approved range")
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("model request requires messages")
        for message in messages:
            if (
                not isinstance(message, dict)
                or set(message) - {"role", "content"}
                or message.get("role") not in {"system", "user", "assistant", "developer"}
                or not isinstance(message.get("content"), str)
            ):
                raise ValueError("only text messages are approved for this route")


class TaskModelTransport(httpx.AsyncBaseTransport):
    """A host-assembled, single-task transport; never supplies live defaults."""

    def __init__(
        self,
        task_id: str,
        context: SubAgentContext,
        *,
        limit: SpendLimit,
        request_limit: int,
        max_pending: int = 1,
        routes: tuple[ChatCompletionsRoute, ...],
        credentials: dict[str, str],
        inner: httpx.AsyncBaseTransport,
    ) -> None:
        if not task_id or not routes or len({route.url for route in routes}) != len(routes):
            raise ValueError("task and unique model routes are required")
        if any(not credentials.get(route.credential_ref) for route in routes):
            raise ValueError("model route credential reference is unresolved")
        self._context = context
        self._task_id = task_id
        self._sent_requests = 0
        self._routes = routes
        self._credentials = dict(credentials)
        self._inner = inner
        if context.budget.limit > 0:
            limit = SpendLimit(min(limit.tokens, context.budget.limit), limit.nano_usd)
        self._ledger = SpendLedger(limit, request_limit=request_limit, max_pending=max_pending)
        context.budget.claim_model_transport()
        self._ledger.start_trial(task_id, limit)
        self._closed = False
        self._closing: asyncio.Task[None] | None = None
        self._inflight: dict[asyncio.Task[httpx.Response], asyncio.Event] = {}

    def snapshot(self) -> ModelSnapshot:
        return {
            **self._ledger.snapshot(),
            "task_id": self._task_id,
            "sent_requests": self._sent_requests,
        }

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._context.check("network")
        if self._closed:
            raise SpendLimitExceeded("transport_closed")
        route = next((route for route in self._routes if route.url == str(request.url)), None)
        if route is None:
            raise ValueError("model destination not approved")
        route.validate(request)
        call_id = uuid4().hex
        self._ledger.reserve(call_id, route.allowance)
        request.headers["Accept-Encoding"] = "identity"
        request.headers["Authorization"] = "Bearer " + self._credentials[route.credential_ref]

        sent = False

        async def receive() -> httpx.Response:
            nonlocal sent
            async with asyncio.timeout_at(self._context.deadline):
                # Task scheduling is an await boundary: recheck immediately before sending.
                self._context.check("network")
                if self._closed:
                    raise SpendLimitExceeded("transport_closed")
                sent = True
                self._sent_requests += 1
                response = await self._inner.handle_async_request(request)
                body = bytearray()
                try:
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise ValueError("compressed model response is not approved")
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > 2_000_000:
                            raise ValueError("model response exceeds byte limit")
                        body.extend(chunk)
                finally:
                    await response.aclose()
                return httpx.Response(
                    response.status_code, headers=response.headers,
                    content=bytes(body), extensions=response.extensions,
                )

        operation = asyncio.create_task(receive())
        cancelled = asyncio.create_task(self._context.cancel.wait())
        settled = asyncio.Event()
        self._inflight[operation] = settled
        try:
            try:
                done, _ = await asyncio.wait(
                    {operation, cancelled}, return_when=asyncio.FIRST_COMPLETED,
                )
                if operation not in done:
                    raise asyncio.CancelledError("task cancelled during model request")
                response = operation.result()
                inputs, outputs = read_usage(response)
            except BaseException:
                if sent:
                    self._ledger.settle(call_id, input_tokens=None, output_tokens=None)
                    self._context.budget.record_unknown(call_id)
                else:
                    self._ledger.release_unsent(call_id)
                raise
            self._ledger.settle(call_id, input_tokens=inputs, output_tokens=outputs)
            self._context.budget.record(call_id, inputs, outputs)
            reason = self._ledger.snapshot()["stop_reason"]
            if reason is not None:
                raise SpendLimitExceeded(reason)
            self._context.check("network")
            if self._closed:
                raise SpendLimitExceeded("transport_closed")
            response.extensions["tank_call_id"] = call_id
            return response
        finally:
            cancelled.cancel()
            operation.cancel()
            await asyncio.gather(operation, cancelled, return_exceptions=True)
            settled.set()
            self._inflight.pop(operation, None)

    async def aclose(self) -> None:
        if self._closing is None:
            self._closed = True
            self._closing = asyncio.create_task(self._close())
        # All close callers see the same outcome; caller cancellation cannot erase cleanup.
        await asyncio.shield(self._closing)

    async def _close(self) -> None:
        inflight = tuple(self._inflight.items())
        for operation, _ in inflight:
            operation.cancel()
        try:
            async with asyncio.timeout(5):
                await asyncio.gather(*(settled.wait() for _, settled in inflight))
                await self._inner.aclose()
        finally:
            self._ledger.close()
            self._credentials.clear()


def read_usage(response: httpx.Response) -> tuple[int, int]:
    if not response.is_success:
        raise ValueError("model response status is not successful")
    data = json_object(response.content)
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        raise ValueError("model response has no trustworthy usage")
    counts: list[int] = []
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if type(value) is not int or value < 0:
            raise ValueError("model response has invalid usage")
        counts.append(value)
    inputs, outputs, total = counts
    if inputs + outputs != total:
        raise ValueError("model response has inconsistent usage")
    return inputs, outputs


def json_object(data: bytes) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    result = json.loads(data, object_pairs_hook=unique)
    if not isinstance(result, dict):
        raise ValueError("JSON object required")
    return result
