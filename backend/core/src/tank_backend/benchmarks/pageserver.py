"""Local HTTP server serving task assets and capturing page side effects.

Benchmark tasks must be zero-external-network: form/browser tasks point at
pages served from the suite's ``assets/`` directory on localhost. Pages
record their side effects back to us:

- ``POST /submit`` with a JSON body  → one JSONL line in the capture file
- ``GET  /click?name=<n>``           → ``{"kind": "click", "name": <n>}`` line

Validators then assert on the capture file — never on pixels.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def _make_handler(assets_dir: Path, capture_path: Path | None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — stdlib name
            pass

        def _record(self, entry: dict[str, Any]) -> None:
            if capture_path is None:
                return
            with capture_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            if self.path.startswith("/click"):
                name = parse_qs(urlparse(self.path).query).get("name", [""])[0]
                self._record({"kind": "click", "name": name, "ts": time.time()})
                self._send(200, b"ok")
                return

            rel = self.path.lstrip("/") or "index.html"
            file = (assets_dir / rel).resolve()
            if not str(file).startswith(str(assets_dir.resolve())) or not file.is_file():
                self._send(404, b"not found")
                return
            body = file.read_bytes()
            self._send(200, body, content_type="text/html; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            if self.path != "/submit":
                self._send(404, b"not found")
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send(400, b"invalid json")
                return
            self._record({"kind": "submit", "payload": payload, "ts": time.time()})
            self._send(200, b"ok")

        def _send(self, status: int, body: bytes, content_type: str = "text/plain") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            # If the page navigated away mid-request (link click racing
            # the fetch), the side effect is already recorded.
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(body)

    return Handler


class LocalPageServer:
    """Serve ``assets_dir`` on localhost and capture page side effects.

    Binding happens in the constructor (port conflicts raise immediately);
    serving runs on a daemon thread. Use as an async context manager —
    the base URL is exposed on enter.
    """

    def __init__(
        self,
        assets_dir: Path,
        capture_path: Path | None,
        port: int,
        host: str = "127.0.0.1",
    ) -> None:
        self._assets_dir = assets_dir
        self._capture_path = capture_path
        self._server = ThreadingHTTPServer(
            (host, port), _make_handler(assets_dir, capture_path)
        )
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="bench-pageserver"
        )
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    async def __aenter__(self) -> str:
        return self.base_url

    async def __aexit__(self, *exc_info: object) -> None:
        self.stop()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
