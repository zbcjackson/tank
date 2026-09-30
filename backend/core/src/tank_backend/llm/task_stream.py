"""SSE forwarding with raw usage validation and the shared task settlement boundary."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .model_transport import ModelCallRecord, TaskModelTransport, _CallState


class TaskStream(httpx.AsyncByteStream):
    def __init__(
        self, owner: TaskModelTransport, call_id: str, state: _CallState,
        response: httpx.Response, settled: asyncio.Event,
    ) -> None:
        self.owner, self.call_id, self.state = owner, call_id, state
        self.response, self.settled = response, settled
        self._closing: asyncio.Task[None] | None = None
        self._read: asyncio.Future[bytes] | None = None
        self._buffer = bytearray()
        self._size = 0
        self._usage: tuple[int, int] | None = None
        self._ended = False
        self._record: ModelCallRecord | None = None

    def _check_open(self) -> None:
        from ..agents.subagent import SubAgentStopped

        self.owner._context.check("network")
        if self.owner._closed:
            raise SubAgentStopped("transport_closed")
        if self._closing is not None and not self._ended:
            raise SubAgentStopped("stream_closed")

    def _inspect(self, chunk: bytes) -> None:
        from .model_transport import json_object, parse_chat_usage

        self._size += len(chunk)
        if self._size > 2_000_000:
            raise ValueError("model response exceeds byte limit")
        self._buffer.extend(chunk)
        while b"\n" in self._buffer:
            line, _, tail = self._buffer.partition(b"\n")
            self._buffer[:] = tail
            line = line.rstrip(b"\r")
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                self._ended = True
            elif data:
                body = json_object(bytes(data))
                if body.get("usage") is not None:
                    self._usage = parse_chat_usage(body["usage"])

    async def __aiter__(self) -> AsyncIterator[bytes]:
        from .model_transport import ModelCaptureError

        cancelled = asyncio.create_task(self.owner._context.cancel.wait())
        iterator = self.response.aiter_bytes()
        try:
            if self.response.headers.get("content-encoding", "identity") != "identity":
                raise ValueError("compressed model response is not approved")
            while True:
                self._check_open()
                self._read = asyncio.ensure_future(anext(iterator))
                async with asyncio.timeout_at(self.owner._context.deadline):
                    done, _ = await asyncio.wait(
                        {self._read, cancelled}, return_when=asyncio.FIRST_COMPLETED,
                    )
                    if self._read not in done:
                        raise asyncio.CancelledError("task cancelled during model stream")
                    self._check_open()
                    try:
                        chunk = self._read.result()
                    except StopAsyncIteration:
                        if self._buffer.strip():
                            self._usage = None
                            raise ValueError("incomplete model stream frame") from None
                        break
                # One HTTP chunk may hold many SSE events. Feed lines separately so
                # SDK buffering cannot bypass the stop check between delivered events.
                for line in chunk.splitlines(keepends=True):
                    self._check_open()
                    try:
                        self._inspect(line)
                    except (TypeError, ValueError):
                        self._usage = None
                        raise
                    if self._ended:
                        await self.aclose()
                        if self.owner._policy is not None:
                            self.owner._policy.check()
                        self._check_open()
                    yield line
                if self._ended:
                    return
        except ModelCaptureError:
            self.owner._context.runtime.stop("capture_failed")
            raise
        finally:
            cancelled.cancel()
            await asyncio.gather(cancelled, return_exceptions=True)
            await self.aclose()
        if self.owner._policy is not None:
            self.owner._policy.check()
        self._check_open()

    async def aclose(self) -> None:
        if self._closing is None:
            self._closing = asyncio.create_task(self._close())
        try:
            await asyncio.shield(self._closing)
        finally:
            if self._record is not None:
                from .model_transport import _completed_call

                _completed_call.set(self._record)

    async def _close(self) -> None:
        try:
            if self._read is not None and not self._read.done():
                self._read.cancel()
                await asyncio.gather(self._read, return_exceptions=True)
            try:
                await self.response.aclose()
            finally:
                inputs, outputs = self._usage if self._usage is not None else (None, None)
                try:
                    self.owner._record_usage(self.call_id, self.state, inputs, outputs)
                finally:
                    self._record = await self.owner._finish(self.call_id, self.state)
        finally:
            self.owner._streams.discard(self)
            self.settled.set()
            self.owner._settling.discard(self.settled)
