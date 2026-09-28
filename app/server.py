"""HTTP serving layer for Second Look: the standard library's ``http.server`` in front of
``secondlook.service``.

The routes themselves live in ``src/secondlook/service.py``, shared with the Lambda
adapter (``deploy/handler.py``), so the two cannot drift. This file only reads a request,
hands ``Service.handle`` the method, path, body and ``Authorization`` header, and writes
the response back. It never mutates a ``Capture``: every state change is a
``process_capture`` or ``invoke(...)`` call made inside the service. The review page's
buttons and the agent's tools reach the same ``invoke``; a reviewer route additionally
needs the reviewer token (``Authorization: Bearer <token>``).

No framework: the runtime dependency set is exactly OpenCV and numpy. State is one
in-memory ``AgentLoop`` per process; a persisted store (``store.py``) is not built.

Routes: see ``secondlook.service``'s docstring (health, review page, pending, capture,
trace, overlay, inspect, retake, approve, reject, resolve_duplicate).

Run directly:  python3 app/server.py     # binds 127.0.0.1:8080; HOST and PORT override
Reviewer token: REVIEWER_TOKEN, or a fresh one generated and printed at startup
Smoke test:    python3 app/smoke.py      # starts its own copy, hits /health + /inspect
"""

from __future__ import annotations

import os
import secrets
import shutil
import signal
import sys
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ENTRY = Path(__file__).resolve().parent.parent
if str(ENTRY / "src") not in sys.path:
    sys.path.insert(0, str(ENTRY / "src"))

from secondlook.agent_loop import AgentLoop  # noqa: E402
from secondlook.service import MAX_BODY_BYTES, Response, Service, json_response  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


class SecondLookServer(ThreadingHTTPServer):
    """Holds the one ``Service`` (and through it the one ``AgentLoop``) every request
    handler thread shares."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        loop: AgentLoop | None = None,
        *,
        reviewer_token: str | None = None,
    ) -> None:
        super().__init__(address, _Handler)
        self._upload_dir = Path(tempfile.mkdtemp(prefix="secondlook-uploads-"))
        self.reviewer_token_generated = not (reviewer_token or os.environ.get("REVIEWER_TOKEN"))
        self.reviewer_token = (
            reviewer_token or os.environ.get("REVIEWER_TOKEN") or secrets.token_urlsafe(18)
        )
        self.service = Service(
            loop=loop or AgentLoop(),
            upload_dir=self._upload_dir,
            static_dir=STATIC_DIR,
            reviewer_token=self.reviewer_token,
        )

    @property
    def loop(self) -> AgentLoop:
        return self.service.loop

    def server_close(self) -> None:
        super().server_close()
        shutil.rmtree(self._upload_dir, ignore_errors=True)


class _Handler(BaseHTTPRequestHandler):
    server: SecondLookServer  # set by http.server on each request

    def log_message(self, format: str, *args: Any) -> None:
        pass  # quiet by default; smoke.py and the tests print their own summaries

    def do_GET(self) -> None:
        self._respond(self.server.service.handle("GET", self._path(), b"", self._auth()))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_BYTES:
            # Drain before answering: the client has sent (or is sending) the whole body,
            # and replying without reading it resets the connection under a still-writing
            # client (ECONNRESET) instead of delivering a clean 413.
            self._drain(length)
            self._respond(
                json_response(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "payload_too_large"})
            )
            return
        body = self.rfile.read(length)
        self._respond(self.server.service.handle("POST", self._path(), body, self._auth()))

    def _path(self) -> str:
        return urlparse(self.path).path

    def _auth(self) -> str | None:
        return self.headers.get("Authorization")

    def _drain(self, length: int) -> None:
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 1 << 20))
            if not chunk:
                break
            remaining -= len(chunk)

    def _respond(self, response: Response) -> None:
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(response.body)


def main() -> int:
    host = os.environ.get("HOST", DEFAULT_HOST)
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    server = SecondLookServer((host, port))
    print(f"second look serving on http://{host}:{port} (Ctrl+C to stop)", flush=True)
    if server.reviewer_token_generated:
        # Printed only when generated here; a token passed in REVIEWER_TOKEN is never echoed.
        print(f"reviewer token for this run: {server.reviewer_token}", flush=True)
    # As a container's PID 1 the process has no default SIGTERM action, so `docker stop`
    # would wait out its timeout and SIGKILL it, skipping server_close and leaving held
    # photos in the upload dir. Routing SIGTERM through KeyboardInterrupt runs the cleanup.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
