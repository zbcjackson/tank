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
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


class _Capture:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.token: str | None = None
        self.secure = False
        self.lock = threading.Lock()

    def route(self, path: str) -> tuple[str | None, str] | None:
        with self.lock:
            if not self.secure:
                return None, path
            prefix = f"/trial/{self.token}/"
            if self.token is None or not path.startswith(prefix):
                return None
            return self.token, "/" + path[len(prefix):].lstrip("/")

    def record(self, token: str | None, entry: dict[str, Any]) -> bool:
        with self.lock:
            if self.secure and (token is None or token != self.token):
                return False
            if self.path is not None:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return True


def _make_handler(assets_dir: Path, capture: _Capture) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — stdlib name
            pass

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            route = capture.route(self.path)
            if route is None:
                self._send(410, b"trial closed or stale token")
                return
            token, path = route
            if urlparse(path).path == "/click":
                name = parse_qs(urlparse(path).query).get("name", [""])[0]
                ok = capture.record(token, {"kind": "click", "name": name, "ts": time.time()})
                self._send(200 if ok else 410, b"ok" if ok else b"trial closed")
                return

            rel = urlparse(path).path.lstrip("/") or "index.html"
            file = (assets_dir / rel).resolve()
            if not file.is_relative_to(assets_dir.resolve()) or not file.is_file():
                self._send(404, b"not found")
                return
            body = file.read_bytes()
            self._send(200, body, content_type="text/html; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            route = capture.route(self.path)
            if route is None:
                self._send(410, b"trial closed or stale token")
                return
            token, path = route
            if path != "/submit":
                self._send(404, b"not found")
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send(400, b"invalid json")
                return
            ok = capture.record(token, {"kind": "submit", "payload": payload, "ts": time.time()})
            self._send(200 if ok else 410, b"ok" if ok else b"trial closed")

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
        self._capture = _Capture(capture_path)
        self._server = ThreadingHTTPServer(
            (host, port), _make_handler(assets_dir, self._capture)
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

    def begin_trial(self, capture_path: Path) -> str:
        with self._capture.lock:
            capture_path.parent.mkdir(parents=True, exist_ok=True)
            capture_path.write_text("", encoding="utf-8")
            self._capture.secure = True
            self._capture.path = capture_path
            self._capture.token = secrets.token_urlsafe(24)
            return f"{self.base_url}/trial/{self._capture.token}"

    def end_trial(self) -> None:
        with self._capture.lock:
            self._capture.token = None
            self._capture.path = None

    async def __aenter__(self) -> str:
        return self.base_url

    async def __aexit__(self, *exc_info: object) -> None:
        self.stop()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
