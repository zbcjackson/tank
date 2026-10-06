"""Task lifetime and accounting for model calls, not HTTP or SSE bytes."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Protocol, TypeVar
from uuid import uuid4

from ..agents.subagent import SubAgentContext, SubAgentStopped
from ..observability.model_observation import call_metadata
from .model_data import ModelRequest, model_payload, model_usage

T = TypeVar("T")


class ModelResponseStream(Protocol):
    def __aiter__(self) -> AsyncIterator[object]: ...
    async def close(self) -> None: ...


class ModelCallPolicy(Protocol):
    def reserve(self, call_id: str, request: ModelRequest) -> None: ...
    def settle(self, call_id: str, inputs: int | None, outputs: int | None) -> None: ...
    def release_unsent(self, call_id: str) -> None: ...
    def check(self) -> None: ...


class ModelCaptureError(RuntimeError):
    """An explicitly required experimental call recorder failed."""


class ModelCapture(Protocol):
    async def request(self, call_id: str, request: ModelRequest) -> None: ...
    async def response(self, call_id: str, response: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class ModelCallRecord:
    task_id: str
    call_id: str
    status: str
    prompt_tokens: int | None
    completion_tokens: int | None
    elapsed_ms: float


_completed_call: ContextVar[ModelCallRecord | None] = ContextVar("task_model_call", default=None)


def get_model_call(task_id: str) -> ModelCallRecord | None:
    result = _completed_call.get()
    return result if result is not None and result.task_id == task_id else None


class _Call:
    def __init__(self, owner: TaskModelCallRunner, request: ModelRequest):
        self.owner, self.request = owner, request
        self.id = uuid4().hex
        self.started = time.monotonic()
        self.attempted = False
        self.reserved = False
        self.value: object = None
        self.usage: tuple[int | None, int | None] = (None, None)
        self.done = asyncio.Event()
        self.finishing = False
        self.record: ModelCallRecord | None = None

    async def begin(self) -> None:
        ctx = self.owner.context
        self.owner.check()
        ctx.observe("model_call", task_id=self.owner.task_id, call_id=self.id, phase="started")
        self.owner.check()
        if ctx.model_policy is not None:
            ctx.model_policy.reserve(self.id, self.request)
            self.reserved = True
        if ctx.model_capture is not None:
            try:
                await ctx.model_capture.request(self.id, self.request)
            except BaseException:
                ctx.runtime.stop("capture_failed")
                raise

    async def finish(self) -> None:
        if self.finishing:
            await self.done.wait()
            if self.record is not None:
                _completed_call.set(self.record)
            return
        self.finishing = True
        ctx = self.owner.context
        inputs, outputs = self.usage
        try:
            if self.attempted:
                if inputs is None or outputs is None:
                    ctx.budget.record_unknown(self.id)
                else:
                    ctx.budget.record(self.id, inputs, outputs)
                if self.reserved and ctx.model_policy is not None:
                    ctx.model_policy.settle(self.id, inputs, outputs)
            elif self.reserved and ctx.model_policy is not None:
                ctx.model_policy.release_unsent(self.id)
            if self.value is not None and ctx.model_capture is not None:
                try:
                    await ctx.model_capture.response(self.id, model_payload(self.value))
                except BaseException:
                    ctx.runtime.stop("capture_failed")
                    raise
        finally:
            record = ModelCallRecord(
                self.owner.task_id,
                self.id,
                "not_started"
                if not self.attempted
                else "returned"
                if inputs is not None
                else "unknown",
                inputs,
                outputs,
                (time.monotonic() - self.started) * 1000,
            )
            self.record = record
            _completed_call.set(record)
            ctx.observe("model_call", phase="finished", **asdict(record))
            self.done.set()


class TaskModelCallRunner:
    """Task-scoped model calls; no credentials or provider protocol."""

    def __init__(self, task_id: str, context: SubAgentContext):
        context.runtime.bind(task_id)
        self.task_id, self.context = task_id, context
        self.closed = False
        self.active: set[asyncio.Future[Any]] = set()
        self.streams: dict[ModelResponseStream, _Call] = {}

    def check(self) -> None:
        self.context.check("network")
        if self.closed:
            raise SubAgentStopped("model_closed")

    async def wait(self, operation: Awaitable[T]) -> T:
        task = asyncio.ensure_future(operation)
        self.active.add(task)
        cancelled = asyncio.create_task(self.context.cancel.wait())
        try:
            async with asyncio.timeout_at(self.context.deadline):
                done, _ = await asyncio.wait({task, cancelled}, return_when=asyncio.FIRST_COMPLETED)
                if cancelled in done:
                    raise asyncio.CancelledError("task cancelled during model call")
                return task.result()
        finally:
            cancelled.cancel()
            if not task.done() and not (isinstance(task, asyncio.Task) and task.cancelling()):
                task.cancel()
            cleanup = asyncio.gather(task, cancelled, return_exceptions=True)
            interrupted = False
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    interrupted = True
            self.active.discard(task)
            if interrupted:
                raise asyncio.CancelledError

    async def run(self, request: ModelRequest, invoke: Callable[[], Awaitable[T]]) -> T:
        call = _Call(self, request)

        async def receive() -> T:
            self.check()
            call.attempted = True
            token = call_metadata.set({"task_id": self.task_id, "call_id": call.id})
            try:
                value = await invoke()
                call.value, call.usage = value, model_usage(value)
                return value
            except Exception as exc:
                call.usage = model_usage(exc)
                raise
            finally:
                call_metadata.reset(token)

        try:
            await call.begin()
            result = await self.wait(receive())
        finally:
            await call.finish()
        self.check()
        return result

    async def stream(
        self, request: ModelRequest, invoke: Callable[[], Awaitable[ModelResponseStream]]
    ) -> AsyncGenerator[object, None]:
        call = _Call(self, request)
        stream: ModelResponseStream | None = None

        async def open_stream() -> ModelResponseStream:
            nonlocal stream
            self.check()
            call.attempted = True
            token = call_metadata.set({"task_id": self.task_id, "call_id": call.id})
            try:
                stream = await invoke()
                self.streams[stream] = call
                return stream
            finally:
                call_metadata.reset(token)

        try:
            await call.begin()
            stream = await self.wait(open_stream())
            self.check()
            assert stream is not None
            iterator = stream.__aiter__()

            async def read_chunk() -> object:
                chunk = await anext(iterator)
                usage = model_usage(chunk)
                if usage[0] is not None:
                    call.usage = usage
                    call.value = chunk
                return chunk

            while True:
                self.check()
                try:
                    chunk = await self.wait(read_chunk())
                except StopAsyncIteration:
                    break
                self.check()
                yield chunk
        finally:
            try:
                if stream is not None and self.streams.pop(stream, None) is not None:
                    await stream.close()
            finally:
                await call.finish()
        self.check()

    async def aclose(self) -> None:
        self.closed = True
        for task in tuple(self.active):
            if not (isinstance(task, asyncio.Task) and task.cancelling()):
                task.cancel()
        await asyncio.gather(*tuple(self.active), return_exceptions=True)
        for stream in tuple(self.streams):
            call = self.streams.pop(stream, None)
            if call is None:
                continue
            try:
                await stream.close()
            finally:
                await call.finish()
