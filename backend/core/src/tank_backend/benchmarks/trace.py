"""Per-trial trace sink: JSONL event log + screenshot archive."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from ..agents.base import AgentOutput
from ..tools.computer_grounding import grounding_call_id

_MAX_CONTENT_CHARS = 2000


class TraceSink:
    """Writes ``trace.jsonl`` and ``screenshots/*.png`` for one trial."""

    def __init__(self, trial_dir: Path) -> None:
        self.trial_dir = trial_dir
        self.trial_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir = trial_dir / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        self._file = (trial_dir / "trace.jsonl").open("a", encoding="utf-8")
        self.screenshot_count = 0
        self._pending: dict[str, _ResponseStream | None] = {}

    def event(self, kind: str, **fields: Any) -> None:
        record = {"ts": time.time(), "kind": kind, **fields}
        self._file.write(
            json.dumps(record, ensure_ascii=False, default=str) + "\n"
        )
        self._file.flush()

    def output(self, output: AgentOutput) -> None:
        self.event(
            "output",
            output_type=output.type.name,
            content=str(output.content)[:_MAX_CONTENT_CHARS],
            metadata=output.metadata,
        )

    def save_screenshot(self, data_url: str) -> str:
        """Decode a ``data:image/png;base64,...`` URL and archive it.

        Returns the path (relative to the trial dir) recorded in the trace.
        """
        self.screenshot_count += 1
        mime = data_url.split(";", 1)[0].removeprefix("data:")
        suffix = {"image/png": "png", "image/webp": "webp", "image/jpeg": "jpg"}.get(mime)
        if suffix is None:
            raise ValueError(f"unsupported screenshot MIME: {mime}")
        name = f"shot_{self.screenshot_count:03d}.{suffix}"
        b64 = data_url.split("base64,", 1)[-1]
        data = base64.b64decode(b64)
        (self.screenshots_dir / name).write_bytes(data)
        rel = f"screenshots/{name}"
        self.event("screenshot", file=rel, mime=mime, sha256=hashlib.sha256(data).hexdigest())
        return rel

    def close(self) -> None:
        if self._file.closed:
            return
        for request_id, archive in list(self._pending.items()):
            if archive is None:
                self.event("http_response", request_id=request_id, body_state="no_response",
                           status_code=None, file=None)
            else:
                archive.finish("trace_closed")
        self._pending.clear()
        self._file.close()

    async def capture_request(self, request: httpx.Request) -> None:
        """Record actual serialized image identity, never headers or image bytes."""
        if self._file.closed:
            return
        body = json.loads(request.content)
        hashes: list[str] = []
        for message in body.get("messages", []):
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if part.get("type") != "image_url":
                    continue
                url = part.get("image_url", {}).get("url", "")
                if url.startswith("data:") and ";base64," in url:
                    image = base64.b64decode(url.split(",", 1)[1])
                    hashes.append(hashlib.sha256(image).hexdigest())
        request_id = uuid.uuid4().hex
        request.extensions["tank_benchmark_trace"] = (self, request_id)
        self._pending[request_id] = None
        self.event("http_request", request_id=request_id, model=body.get("model"),
                   stream=bool(body.get("stream")), image_sha256=hashes,
                   grounding_call_id=grounding_call_id.get())

    async def capture_response(self, response: httpx.Response) -> None:
        """Preserve the body before SDK parsing, linked to its actual HTTP attempt."""
        binding = response.request.extensions.get("tank_benchmark_trace")
        if binding is None or self._file.closed:
            return
        owner, request_id = binding
        if owner is not self or request_id not in self._pending:
            return
        archive = _ResponseStream(self, request_id, response)
        self._pending[request_id] = archive
        if response.is_stream_consumed:
            # In-memory transports may return an already-read body.
            archive.write(response.content)
            archive.finish("complete")
        else:
            response.stream = archive


class _ResponseStream(httpx.AsyncByteStream):
    """Tee bytes before SDK parsing without buffering ahead of the consumer."""

    def __init__(self, sink: TraceSink, request_id: str, response: httpx.Response) -> None:
        if not isinstance(response.stream, httpx.AsyncByteStream):
            raise TypeError("Benchmark response requires an async stream")
        self.inner = response.stream
        self.sink, self.request_id = sink, request_id
        self.status_code = response.status_code
        self.content_type = response.headers.get("content-type")
        self.content_encoding = response.headers.get("content-encoding")
        self.representation = "httpx_decoded" if response.is_stream_consumed else "httpx_raw"
        self.relative = f"responses/{request_id}.bin"
        (sink.trial_dir / "responses").mkdir(exist_ok=True)
        self.file = (sink.trial_dir / self.relative).open("xb")
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, chunk: bytes) -> None:
        if self.file.closed:
            return
        self.file.write(chunk)
        self.file.flush()
        self.digest.update(chunk)
        self.size += len(chunk)

    def finish(self, state: str, error: str | None = None) -> None:
        if self.file.closed:
            return
        self.file.close()
        self.sink._pending.pop(self.request_id, None)
        self.sink.event("http_response", request_id=self.request_id,
                        status_code=self.status_code, file=self.relative, body_state=state,
                        bytes=self.size, sha256=self.digest.hexdigest(), error_type=error,
                        content_type=self.content_type, content_encoding=self.content_encoding,
                        body_representation=self.representation)

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self.inner:
                self.write(chunk)
                yield chunk
        except asyncio.CancelledError:
            self.finish("cancelled", "CancelledError")
            raise
        except Exception as exc:
            self.finish("read_error", type(exc).__name__)
            raise
        else:
            self.finish("complete")

    async def aclose(self) -> None:
        try:
            await self.inner.aclose()
        finally:
            self.finish("closed_early")
