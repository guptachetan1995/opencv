"""HTTP serving layer for Second Look.

Exposes the agent loop over HTTP: ``POST /inspect`` runs perception -> decision ->
action on a posted photo, ``GET /trace/<capture_id>`` and ``GET /pending`` read state, and
``POST /approve/<capture_id>`` is the human's approval — through the *same*
``secondlook.agent_loop.invoke("approve", ..., actor="reviewer")`` call the approval page's
button hits and the agent's own tools would hit with ``actor="agent"``: agent and human
share one surface. This module never mutates a ``Capture`` itself; every state change
happens by calling ``process_capture`` or ``invoke``, both imported unchanged from
``agent_loop.py``.

A local dev server, not the Lambda handler (that is ``deploy/handler.py``): no AWS SDK, no
S3, no framework. The runtime dependency set is exactly OpenCV and numpy, and the web layer
is one static HTML file with vanilla JavaScript, so this uses only the standard library's
``http.server``. State is one in-memory ``AgentLoop`` per process; a persisted store
(``store.py``) is not built.

Routes:
    GET  /health              -> {"status": "ok"}
    GET  /, /review           -> the approval page (static/review.html)
    GET  /pending             -> escalated captures waiting for a reviewer
    GET  /trace/<capture_id>  -> the capture's full trace (a list of TraceEntry rows)
    POST /inspect             -> body: raw image bytes; runs process_capture, returns the
                                 capture's state, measurements and verdict
    POST /approve/<capture_id> -> body: optional JSON {"note": str}; the human approval

Run directly:  python3 app/server.py            # binds 127.0.0.1:8080 (PORT overrides)
Smoke test:    python3 app/smoke.py             # starts its own copy, hits /health + /inspect
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ENTRY = Path(__file__).resolve().parent.parent
if str(ENTRY / "src") not in sys.path:
    sys.path.insert(0, str(ENTRY / "src"))

from secondlook.agent_loop import AgentLoop, Capture, invoke, process_capture  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY_BYTES = 4 * 1024 * 1024  # mirrors deploy/handler.py's Lambda payload guard, for parity
DEFAULT_PORT = 8080


class _JSONError(Exception):
    """Raised by a route handler to short-circuit straight to an HTTP error response."""

    def __init__(self, status: HTTPStatus, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.error = error


def _capture_public(cap: Capture) -> dict[str, Any]:
    """The one JSON shape a ``Capture`` takes over HTTP — used by ``/inspect``,
    ``/pending`` and ``/approve`` so the three routes can't drift into different shapes for
    the same object. Never includes ``image_path``: a local filesystem detail, not
    evidence (the records store only derived measurements, never the image itself)."""
    return {
        "capture_id": cap.capture_id,
        "batch_id": cap.batch_id,
        "parent_id": cap.parent_id,
        "attempt": cap.attempt,
        "state": cap.state,
        "review_reason": cap.review_reason,
        "measurements": cap.measurements.to_dict() if cap.measurements else None,
        "verdict": cap.verdict.to_dict() if cap.verdict else None,
    }


class SecondLookServer(ThreadingHTTPServer):
    """Holds the one ``AgentLoop`` every request handler reads, and mutates only through
    ``invoke``/``process_capture`` — never directly."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], loop: AgentLoop | None = None) -> None:
        super().__init__(address, _Handler)
        self.loop = loop or AgentLoop()
        self._upload_dir = Path(tempfile.mkdtemp(prefix="secondlook-uploads-"))

    def save_upload(self, body: bytes) -> Path:
        """Writes posted image bytes to a temp file — ``Capture.image_path`` is a
        filesystem path (``inspect_file`` calls ``cv2.imread`` on it), not bytes."""
        path = self._upload_dir / f"{uuid.uuid4().hex}.jpg"
        path.write_bytes(body)
        return path

    def server_close(self) -> None:
        super().server_close()
        shutil.rmtree(self._upload_dir, ignore_errors=True)


class _Handler(BaseHTTPRequestHandler):
    server: SecondLookServer  # set by http.server on each request

    def log_message(self, format: str, *args: Any) -> None:
        pass  # quiet by default; smoke.py and the tests print their own summaries

    def do_GET(self) -> None:
        self._dispatch(self._route_get)

    def do_POST(self) -> None:
        self._dispatch(self._route_post)

    def _dispatch(self, route: Any) -> None:
        try:
            route()
        except _JSONError as exc:
            self._send_json(exc.status, {"error": exc.error})
        except KeyError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"unknown capture_id: {exc}"})
        except (RuntimeError, PermissionError, ValueError) as exc:
            self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except Exception as exc:  # boundary of last resort — never a bare socket hang
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    # ---- routing --------------------------------------------------------------------

    def _route_get(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
        elif path in ("/", "/review"):
            self._send_html(HTTPStatus.OK, (STATIC_DIR / "review.html").read_text())
        elif path == "/pending":
            self._send_json(HTTPStatus.OK, self._pending())
        elif path.startswith("/trace/"):
            self._send_json(HTTPStatus.OK, self._trace(path.removeprefix("/trace/")))
        else:
            raise _JSONError(HTTPStatus.NOT_FOUND, "not_found")

    def _route_post(self) -> None:
        path = urlparse(self.path).path
        if path == "/inspect":
            self._inspect()
        elif path.startswith("/approve/"):
            self._approve(path.removeprefix("/approve/"))
        else:
            raise _JSONError(HTTPStatus.NOT_FOUND, "not_found")

    # ---- handlers ---------------------------------------------------------------------

    def _pending(self) -> list[dict[str, Any]]:
        loop = self.server.loop
        return [_capture_public(cap) for cap in loop.captures.values() if cap.state == "escalated"]

    def _trace(self, capture_id: str) -> list[dict[str, Any]]:
        loop = self.server.loop
        if capture_id not in loop.captures:
            raise _JSONError(HTTPStatus.NOT_FOUND, f"unknown capture_id: {capture_id}")
        return invoke("get_trace", {"capture_id": capture_id}, "agent", loop=loop)

    def _inspect(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_BYTES:
            # Drain the socket before responding: the client already sent (or is sending)
            # the whole body, and answering without reading it closes the connection out
            # from under a still-writing client (ECONNRESET) instead of a clean 413.
            self._drain(length)
            raise _JSONError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "payload_too_large")
        body = self.rfile.read(length)
        if not body:
            raise _JSONError(HTTPStatus.BAD_REQUEST, "empty body: post raw image bytes")

        loop = self.server.loop
        image_path = self.server.save_upload(body)
        try:
            capture_id = loop.open_capture(image_path)
            # The same loop driver tools/run_demo.py calls — perception's verdict picks
            # the next invoke() call, this route never re-implements that sequence.
            cap = process_capture(capture_id, loop=loop)
            self._send_json(HTTPStatus.OK, _capture_public(cap))
        finally:
            # Each image is read once, inside process_capture (inspect_capture and, on a
            # retake, compare_captures) — nothing touches the file again afterward, so
            # it's safe to remove here rather than only at server shutdown.
            image_path.unlink(missing_ok=True)

    def _approve(self, capture_id: str) -> None:
        loop = self.server.loop
        if capture_id not in loop.captures:
            raise _JSONError(HTTPStatus.NOT_FOUND, f"unknown capture_id: {capture_id}")
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_BYTES:
            self._drain(length)
            raise _JSONError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "payload_too_large")
        payload = json.loads(self.rfile.read(length)) if length else {}
        note = payload.get("note")
        # The SAME invoke() the agent tools call — actor="reviewer" instead of "agent" is
        # the only difference, and it's what makes this a human-only verb, not a route with
        # its own mutation path.
        invoke("approve", {"capture_id": capture_id, "note": note}, "reviewer", loop=loop)
        self._send_json(HTTPStatus.OK, _capture_public(loop.captures[capture_id]))

    # ---- response helpers ---------------------------------------------------------------

    def _drain(self, length: int) -> None:
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 1 << 20))
            if not chunk:
                break
            remaining -= len(chunk)

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: HTTPStatus, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    server = SecondLookServer(("127.0.0.1", port))
    print(f"second look serving on http://127.0.0.1:{port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
