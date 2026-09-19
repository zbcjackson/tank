"""Per-trial trace sink: JSONL event log + screenshot archive."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from ..agents.base import AgentOutput

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
        self._file.close()

    async def capture_request(self, request: httpx.Request) -> None:
        """Record actual serialized image identity, never headers or image bytes."""
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
        self.event("http_request", model=body.get("model"), image_sha256=hashes)
