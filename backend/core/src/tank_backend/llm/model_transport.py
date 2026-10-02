"""Task-owned model HTTP admission. Protocol data never enters the shared ledger."""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import math
import time
from collections import deque
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict
from uuid import uuid4

import httpx

from ..agents.subagent import SubAgentContext, SubAgentStopped
from ..agents.task_runtime import ExecutionRecord

if TYPE_CHECKING:
    from .task_stream import TaskStream


class ModelCallPolicy(Protocol):
    """Optional caller-owned admission policy, independent of token accounting."""

    def reserve(self, call_id: str, request: httpx.Request) -> None: ...
    def settle(self, call_id: str, inputs: int | None, outputs: int | None) -> None: ...
    def release_unsent(self, call_id: str) -> None: ...
    def check(self) -> None: ...


class ModelCaptureError(RuntimeError):
    """Required wire capture failed; no later business request may proceed."""


class ModelCapture(Protocol):
    async def request(self, call_id: str, request: httpx.Request) -> None: ...
    async def response(self, call_id: str, response: httpx.Response) -> None: ...


class ModelSnapshot(TypedDict):
    task_id: str
    sent_requests: int
    usage: dict[str, int]


@dataclass(frozen=True)
class ModelCallRecord:
    """Transport outcome and measured usage, not a claim of semantic completion."""

    task_id: str
    call_id: str
    status: Literal["not_sent", "unknown", "returned"]
    prompt_tokens: int | None
    completion_tokens: int | None
    elapsed_ms: float


_completed_call: ContextVar[ModelCallRecord | None] = ContextVar("task_model_call", default=None)


def get_model_call(task_id: str) -> ModelCallRecord | None:
    """Return this coroutine's completed call, never another concurrent request's record."""
    record = _completed_call.get()
    return record if record is not None and record.task_id == task_id else None


@dataclass
class _CallState:
    started: float
    finished: bool = False
    sent: bool = False
    inputs: int | None = None
    outputs: int | None = None
    response: httpx.Response | None = None
    streaming: bool = False


@dataclass(frozen=True)
class ChatCompletionsRoute:
    url: str
    model: str
    credential_ref: str
    max_output_tokens: int | None = None
    max_upload_bytes: int = 65536
    allow_images: bool = False
    allow_tools: bool = False
    allow_stream: bool = False
    allow_http: bool = False
    extra_parameters: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        url = httpx.URL(self.url)
        if (
            (url.scheme != "https" and not (self.allow_http and url.scheme == "http"))
            or not url.host or url.userinfo or url.query or url.fragment
            or not self.model or not self.credential_ref
            or (self.max_output_tokens is not None and (
                type(self.max_output_tokens) is not int or self.max_output_tokens <= 0
            ))
            or type(self.max_upload_bytes) is not int or self.max_upload_bytes <= 0
        ):
            raise ValueError("model route requires an exact HTTPS endpoint and bounded upload")
        if set(self.extra_parameters) & {
            "model", "messages", "max_tokens", "max_completion_tokens", "stream", "temperature",
        }:
            raise ValueError("provider parameters cannot override core model fields")
        object.__setattr__(self, "extra_parameters", copy.deepcopy(self.extra_parameters))

    def validate(self, request: httpx.Request) -> None:
        if request.method != "POST" or len(request.content) > self.max_upload_bytes:
            raise ValueError("model request method or upload size rejected")
        data = json_object(request.content)
        maximum = data.get("max_tokens", data.get("max_completion_tokens"))
        if (
            data.get("model") != self.model
            or type(data.get("stream", False)) is not bool
            or (data.get("stream", False) and not self.allow_stream)
            or ("max_tokens" in data and "max_completion_tokens" in data)
            or type(maximum) is not int or maximum <= 0
            or (self.max_output_tokens is not None and isinstance(maximum, int)
                and maximum > self.max_output_tokens)
            or set(data) - (
                {"model", "messages", "max_tokens", "max_completion_tokens",
                 "stream", "temperature"}
                | set(self.extra_parameters)
                | ({"tools", "tool_choice", "parallel_tool_calls"} if self.allow_tools else set())
                | ({"stream_options"} if self.allow_stream else set())
            )
            or any(key in data and data[key] != value
                   for key, value in self.extra_parameters.items())
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
            fields = {"role", "content"}
            roles = {"system", "user", "assistant", "developer"}
            if self.allow_tools:
                fields |= {
                    "tool_calls", "tool_call_id", "name", "reasoning",
                    "reasoning_content", "metadata",
                }
                roles.add("tool")
            if (
                not isinstance(message, dict) or set(message) - fields
                or message.get("role") not in roles
            ):
                raise ValueError("message outside approved protocol")
            content = message.get("content")
            if content is None and self.allow_tools and message.get("tool_calls"):
                continue
            if isinstance(content, str):
                continue
            if not self.allow_images or not isinstance(content, list) or not content:
                raise ValueError("only text messages are approved for this route")
            for part in content:
                if not isinstance(part, dict):
                    raise ValueError("invalid content part")
                if part.get("type") == "text" and set(part) == {"type", "text"}:
                    if not isinstance(part["text"], str):
                        raise ValueError("text content must be a string")
                    continue
                if part.get("type") != "image_url" or set(part) != {"type", "image_url"}:
                    raise ValueError("unapproved content category")
                value = part["image_url"]
                if not isinstance(value, dict) or set(value) - {"url", "detail"}:
                    raise ValueError("invalid image content")
                url = value.get("url")
                if not isinstance(url, str):
                    raise ValueError("image must be an inline data URL")
                prefix, separator, encoded = url.partition(",")
                if not separator or prefix not in {
                    "data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64",
                } or not encoded:
                    raise ValueError("only approved inline images may be uploaded")
                base64.b64decode(encoded, validate=True)


class TaskModelTransport(httpx.AsyncBaseTransport):
    """A host-assembled, single-task transport; never supplies live defaults."""

    def __init__(
        self,
        task_id: str,
        context: SubAgentContext,
        *,
        policy: ModelCallPolicy | None = None,
        routes: tuple[ChatCompletionsRoute, ...],
        credentials: dict[str, str],
        inner: httpx.AsyncBaseTransport,
    ) -> None:
        if not task_id or not routes or len({route.url for route in routes}) != len(routes):
            raise ValueError("task and unique model routes are required")
        if any(not credentials.get(route.credential_ref) for route in routes):
            raise ValueError("model route credential reference is unresolved")
        context.runtime.bind(task_id)
        self._context = context
        self._task_id = task_id
        self._sent_requests = 0
        self._records: deque[ModelCallRecord] = deque(maxlen=128)
        self._routes = routes
        self._credentials = dict(credentials)
        self._inner = inner
        if (policy is not None and context.model_policy is not None
                and context.model_policy is not policy):
            raise ValueError("model policy differs from the task policy")
        self._policy = context.model_policy if context.model_policy is not None else policy
        self._closed = False
        self._closing: asyncio.Task[None] | None = None
        self._inflight: set[asyncio.Task[httpx.Response]] = set()
        self._settling: set[asyncio.Event] = set()
        self._streams: set[TaskStream] = set()

    def snapshot(self) -> ModelSnapshot:
        return {
            "usage": self._context.budget.snapshot(),
            "task_id": self._task_id,
            "sent_requests": self._sent_requests,
        }

    @property
    def records(self) -> tuple[ModelCallRecord, ...]:
        """Latest 128 terminal records; authoritative totals remain in the task ledger."""
        return tuple(self._records)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._context.check("network")
        if self._closed:
            raise SubAgentStopped("transport_closed")
        call_id = uuid4().hex
        state = _CallState(started=time.monotonic())
        settled = asyncio.Event()
        self._settling.add(settled)
        try:
            self._context.observe(
                "model_call", task_id=self._task_id, call_id=call_id, phase="started",
            )
            streaming = await self._prepare(request, call_id)
            if streaming:
                return await self._start_stream(request, call_id, state, settled)
            return await self._request(request, call_id, state)
        finally:
            if not state.streaming:
                try:
                    if not state.finished:
                        await self._finish(call_id, state)
                finally:
                    settled.set()
                    self._settling.discard(settled)

    async def _finish(self, call_id: str, state: _CallState) -> ModelCallRecord:
        state.finished = True
        record = ModelCallRecord(
            self._task_id, call_id,
            "not_sent" if not state.sent else (
                "returned" if state.inputs is not None else "unknown"
            ),
            state.inputs, state.outputs, (time.monotonic() - state.started) * 1000,
        )
        self._records.append(record)
        try:
            if not self._context.runtime.audit_failed:
                await self._context.runtime.write_audit(ExecutionRecord(
                    record.task_id, record.call_id, "chat_completions", record.status,
                    category="model", phase="finished", prompt_tokens=record.prompt_tokens,
                    completion_tokens=record.completion_tokens, elapsed_ms=record.elapsed_ms,
                ))
        finally:
            _completed_call.set(record)
            self._context.observe("model_call", phase="finished", **asdict(record))
        return record

    async def _prepare(self, request: httpx.Request, call_id: str) -> bool:
        self._context.check("network")
        if self._closed:
            raise SubAgentStopped("transport_closed")
        route = next((route for route in self._routes if route.url == str(request.url)), None)
        if route is None:
            raise ValueError("model destination not approved")
        route.validate(request)
        request.headers["Accept-Encoding"] = "identity"
        request.headers["Authorization"] = "Bearer " + self._credentials[route.credential_ref]
        if self._policy is not None:
            self._policy.reserve(call_id, request)
        return json_object(request.content).get("stream") is True


    async def _send(
        self, request: httpx.Request, call_id: str, state: _CallState,
    ) -> httpx.Response:
        await self._context.runtime.write_audit(ExecutionRecord(
            self._task_id, call_id, "chat_completions", "not_sent",
            category="model", phase="prepared",
        ))
        capture = self._context.model_capture
        if capture is not None:
            try:
                await capture.request(call_id, request)
            except BaseException:
                self._context.runtime.stop("capture_failed")
                raise
        self._context.check("network")
        await self._context.runtime.write_audit(ExecutionRecord(
            self._task_id, call_id, "chat_completions", "unknown",
            category="model", phase="dispatch",
        ))
        # Audit writes are await boundaries: recheck immediately before sending.
        self._context.check("network")
        if self._closed:
            raise SubAgentStopped("transport_closed")
        state.sent = True
        self._sent_requests += 1
        response = await self._inner.handle_async_request(request)
        response.request = request
        state.response = response
        if capture is not None:
            try:
                await capture.response(call_id, response)
            except asyncio.CancelledError:
                await response.aclose()
                raise
            except Exception:
                # Read an already received response so trustworthy usage is not lost.
                self._context.runtime.stop("capture_failed")
        return response

    async def _request(
        self, request: httpx.Request, call_id: str, state: _CallState,
    ) -> httpx.Response:

        async def receive() -> httpx.Response:
            async with asyncio.timeout_at(self._context.deadline):
                response = await self._send(request, call_id, state)
                body = bytearray()
                try:
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise ValueError("compressed model response is not approved")
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > 2_000_000:
                            raise ValueError("model response exceeds byte limit")
                        body.extend(chunk)
                except ModelCaptureError:
                    self._context.runtime.stop("capture_failed")
                    raise
                finally:
                    await response.aclose()
                return httpx.Response(
                    response.status_code, headers=response.headers,
                    content=bytes(body), extensions=response.extensions,
                )

        operation = asyncio.create_task(receive())
        cancelled = asyncio.create_task(self._context.cancel.wait())
        self._inflight.add(operation)
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
                if state.sent:
                    inputs = outputs = None
                    # Cancellation may win the waiter race after a complete response arrived.
                    if operation.done() and not operation.cancelled():
                        with suppress(Exception):
                            inputs, outputs = read_usage(operation.result())
                    if inputs is None and state.response is not None:
                        with suppress(Exception):
                            encoding = state.response.headers.get("content-encoding", "identity")
                            if (encoding == "identity"
                                    and len(state.response.content) <= 2_000_000):
                                inputs, outputs = read_usage(state.response)
                    self._record_usage(call_id, state, inputs, outputs)
                else:
                    if self._policy is not None:
                        self._policy.release_unsent(call_id)
                raise
            self._record_usage(call_id, state, inputs, outputs)
            if self._policy is not None:
                self._policy.check()
            response.extensions["tank_call_id"] = call_id
        finally:
            cancelled.cancel()
            if not operation.cancelling():
                operation.cancel()
            cleanup = asyncio.gather(operation, cancelled, return_exceptions=True)
            interrupted = False
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    interrupted = True
            try:
                await self._finish(call_id, state)
            finally:
                self._inflight.discard(operation)
            if interrupted:
                raise asyncio.CancelledError
        self._context.check("network")
        if self._closed:
            raise SubAgentStopped("transport_closed")
        return response

    async def _start_stream(
        self, request: httpx.Request, call_id: str, state: _CallState, settled: asyncio.Event,
    ) -> httpx.Response:
        from .task_stream import TaskStream

        async def headers() -> httpx.Response:
            async with asyncio.timeout_at(self._context.deadline):
                return await self._send(request, call_id, state)

        operation = asyncio.create_task(headers())
        cancelled = asyncio.create_task(self._context.cancel.wait())
        self._inflight.add(operation)
        try:
            done, _ = await asyncio.wait(
                {operation, cancelled}, return_when=asyncio.FIRST_COMPLETED,
            )
            if operation not in done:
                raise asyncio.CancelledError("task cancelled during model request")
            response = operation.result()
            self._context.check("network")
            if self._closed:
                raise SubAgentStopped("transport_closed")
            if (not response.is_success or
                    "text/event-stream" not in response.headers.get("content-type", "")):
                await response.aclose()
                raise ValueError("invalid streaming model response")
            stream = TaskStream(self, call_id, state, response, settled)
            self._streams.add(stream)
            state.streaming = True
            return httpx.Response(
                response.status_code, headers=response.headers, stream=stream, request=request,
                extensions={**response.extensions, "tank_call_id": call_id},
            )
        except BaseException:
            if state.sent:
                self._record_usage(call_id, state, None, None)
            elif self._policy is not None:
                self._policy.release_unsent(call_id)
            raise
        finally:
            cancelled.cancel()
            if not operation.done() and not operation.cancelling():
                operation.cancel()
            await asyncio.gather(operation, cancelled, return_exceptions=True)
            if not state.streaming and state.response is not None:
                await state.response.aclose()
            self._inflight.discard(operation)

    def _record_usage(
        self, call_id: str, state: _CallState, inputs: int | None, outputs: int | None,
    ) -> None:
        state.inputs, state.outputs = inputs, outputs
        if inputs is None or outputs is None:
            self._context.budget.record_unknown(call_id)
        else:
            self._context.budget.record(call_id, inputs, outputs)
        if self._policy is not None:
            self._policy.settle(call_id, inputs, outputs)

    async def aclose(self) -> None:
        if self._closing is None:
            self._closed = True
            self._closing = asyncio.create_task(self._close())
        # All close callers see the same outcome; caller cancellation cannot erase cleanup.
        await asyncio.shield(self._closing)

    async def _close(self) -> None:
        inflight = tuple(self._inflight)
        settling = tuple(self._settling)
        for operation in inflight:
            if not operation.cancelling():
                operation.cancel()
        try:
            async with asyncio.timeout(5):
                await asyncio.gather(*(stream.aclose() for stream in tuple(self._streams)))
                await asyncio.gather(*(settled.wait() for settled in settling))
                await self._inner.aclose()
        finally:
            self._credentials.clear()


def read_usage(response: httpx.Response) -> tuple[int, int]:
    if not response.is_success:
        raise ValueError("model response status is not successful")
    data = json_object(response.content)
    return parse_chat_usage(data.get("usage"))


def parse_chat_usage(usage: object) -> tuple[int, int]:
    """Validate raw Chat Completions counts before SDK coercion or accounting."""
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


def json_object(data: str | bytes) -> dict[str, object]:
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
