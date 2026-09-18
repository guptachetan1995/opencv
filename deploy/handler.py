"""Lambda Function URL entry point for Second Look (#46/#47).

Interim stand-in for SPEC §12's reserved ``src/secondlook/handler.py`` — that module is
still unbuilt (SPEC's own "Built so far" paragraph calls it a follow-up goal), and #46 is
scoped away from creating files under ``src/`` or ``app/`` (parallel-safety with sibling
in-flight goals). This wraps the same ``secondlook.agent_loop`` chokepoint
``app/server.py`` uses for local dev (``POST /inspect`` -> ``process_capture``,
``POST /approve/<id>`` -> ``invoke("approve", ..., actor="reviewer")``), translated from
``http.server``'s request/response shape to the Lambda Function URL event/response shape
(payload format 2.0). When ``src/secondlook/handler.py`` is eventually built, its routes
fold in from here and ``deploy/Dockerfile``'s COPY + CMD move in the same PR — until then
this file is the real Lambda entry point SPEC §9 describes.

Differs from ``app/server.py`` only where Lambda forces a difference:
  - Uploads go to ``/tmp`` (the only writable path in a Lambda execution environment).
  - No manual ``sys.path`` insert: the Dockerfile copies ``secondlook/`` directly under
    ``${LAMBDA_TASK_ROOT}``, already on the Lambda Python runtime's ``sys.path``.
  - The module-level ``AgentLoop`` persists only for one warm execution environment's
    lifetime; concurrent Lambda executions get independent, non-shared state. This is not
    a regression this goal introduces — ``agent_loop.py``'s own docstring already scopes
    it as an in-memory precursor, and SPEC §9's S3 upgrade path (``store.py``, unbuilt)
    is what actually fixes it.
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any

from secondlook.agent_loop import AgentLoop, Capture, invoke, process_capture

STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = Path("/tmp/secondlook-uploads")  # noqa: S108 -- the only writable Lambda path
MAX_BODY_BYTES = 4 * 1024 * 1024  # mirrors app/server.py's SPEC §9 payload guard

_loop = AgentLoop()


class _HandlerError(Exception):
    def __init__(self, status: int, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.error = error


def _capture_public(cap: Capture) -> dict[str, Any]:
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


def _json(status: int, payload: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _html(status: int, body: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": body,
    }


def _route_get(path: str) -> dict[str, Any]:
    if path == "/health":
        return _json(200, {"status": "ok"})
    if path in ("/", "/review"):
        return _html(200, (STATIC_DIR / "review.html").read_text())
    if path == "/pending":
        pending = [_capture_public(c) for c in _loop.captures.values() if c.state == "escalated"]
        return _json(200, pending)
    if path.startswith("/trace/"):
        capture_id = path.removeprefix("/trace/")
        if capture_id not in _loop.captures:
            raise _HandlerError(404, f"unknown capture_id: {capture_id}")
        return _json(200, invoke("get_trace", {"capture_id": capture_id}, "agent", loop=_loop))
    raise _HandlerError(404, "not_found")


def _decode_body(event: dict[str, Any]) -> bytes:
    raw = event.get("body") or ""
    return base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("utf-8")


def _inspect(event: dict[str, Any]) -> dict[str, Any]:
    body = _decode_body(event)
    # Unlike app/server.py's Content-Length pre-check, this can't reject before reading:
    # a Function URL event hands over the body already materialized in the event dict,
    # with no socket to pre-check before it's in memory. Lambda's own 6 MB hard payload
    # cap is the real backstop regardless of what this check does.
    if len(body) > MAX_BODY_BYTES:
        raise _HandlerError(413, "payload_too_large")
    if not body:
        raise _HandlerError(400, "empty body: post raw image bytes")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(body)
    try:
        capture_id = _loop.open_capture(image_path)
        cap = process_capture(capture_id, loop=_loop)
        return _json(200, _capture_public(cap))
    finally:
        # A warm Lambda execution environment persists across many invocations with no
        # equivalent of app/server.py's shutdown-time rmtree — leaving this file behind
        # would accumulate one per invocation in /tmp until the environment recycles.
        # Each image is read once, inside process_capture, so it's safe to remove here.
        image_path.unlink(missing_ok=True)


def _approve(path: str, event: dict[str, Any]) -> dict[str, Any]:
    capture_id = path.removeprefix("/approve/")
    if capture_id not in _loop.captures:
        raise _HandlerError(404, f"unknown capture_id: {capture_id}")
    body = _decode_body(event)
    if len(body) > MAX_BODY_BYTES:
        raise _HandlerError(413, "payload_too_large")
    payload = json.loads(body) if body else {}
    invoke(
        "approve",
        {"capture_id": capture_id, "note": payload.get("note")},
        "reviewer",
        loop=_loop,
    )
    return _json(200, _capture_public(_loop.captures[capture_id]))


def _route_post(path: str, event: dict[str, Any]) -> dict[str, Any]:
    if path == "/inspect":
        return _inspect(event)
    if path.startswith("/approve/"):
        return _approve(path, event)
    raise _HandlerError(404, "not_found")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """The Lambda entry point named by ``deploy/Dockerfile``'s ``CMD``."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    try:
        if method == "GET":
            return _route_get(path)
        if method == "POST":
            return _route_post(path, event)
        return _json(404, {"error": "not_found"})
    except _HandlerError as exc:
        return _json(exc.status, {"error": exc.error})
    except KeyError as exc:
        return _json(404, {"error": f"unknown capture_id: {exc}"})
    except (RuntimeError, PermissionError, ValueError) as exc:
        return _json(409, {"error": str(exc)})
    except Exception as exc:  # boundary of last resort, mirrors app/server.py's
        return _json(500, {"error": str(exc)})
