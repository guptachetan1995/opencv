"""The HTTP routes, written once for both serving adapters.

``app/server.py`` (the standard library's ``http.server``: ``make run`` locally, and the
EC2 deploy) and ``deploy/handler.py`` (a Lambda Function URL) are thin adapters. Each turns
its own request shape into one ``Service.handle(method, path, body, authorization)`` call
and writes the ``Response`` back. Apart from putting an arriving photo into a slot
(``AgentLoop.open_capture`` / ``attach_image``, which decide nothing), every state change a
route makes is a ``process_capture`` or ``invoke(...)`` call into ``agent_loop``; this module
never sets a ``Capture`` field itself.

Routes:
    GET  /health                   {"status": "ok"}
    GET  /, /review                the review page (static/review.html)
    GET  /pending                  escalated captures waiting for a reviewer
    GET  /capture/<id>             one capture (the get_capture read tool)
    GET  /trace/<id>               the capture's trace chain (the get_trace read tool)
    GET  /overlay/<id>             reviewer only: the evidence overlay JPEG, drawn per request
    POST /inspect                  raw image bytes; runs process_capture
    POST /retake/<successor_id>    raw image bytes for the slot request_recapture opened
    POST /approve/<id>             reviewer only: {"note"}                  -> invoke("approve")
    POST /reject/<id>              reviewer only: {"note"}                  -> invoke("reject")
    POST /resolve_duplicate/<id>   reviewer only: {"is_duplicate", "note"}  -> invoke(...)

Reviewer routes need ``Authorization: Bearer <reviewer token>``. Without it they answer
401 and nothing is called, so ``actor="reviewer"`` means "a person holding the reviewer's
token", not "anyone who can reach the URL". With no token configured at all, the reviewer
routes are closed.

Photos. An upload is deleted as soon as the loop has read it, unless the capture
escalated: then it is held in the adapter's temporary directory (never in a record) so the
reviewer can see it, and deleted the moment the capture leaves the review queue. At most
``MAX_HELD_PHOTOS`` are held; past that the oldest is deleted and its overlay answers 410.
"""

from __future__ import annotations

import hmac
import json
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any

from secondlook import overlay
from secondlook.agent_loop import AgentLoop, capture_view, invoke, process_capture

MAX_BODY_BYTES = 4 * 1024 * 1024  # under Lambda's 6 MB synchronous payload cap
MAX_HELD_PHOTOS = 64
REVIEWER_VERBS = ("approve", "reject", "resolve_duplicate")
_BEARER_CHALLENGE = {"WWW-Authenticate": 'Bearer realm="second-look-reviewer"'}


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    content_type: str = "application/json"
    headers: dict[str, str] = field(default_factory=dict)


class RouteError(Exception):
    """Raised inside a route to answer with a specific status and error message."""

    def __init__(self, status: int, error: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(error)
        self.status = status
        self.error = error
        self.headers = headers or {}


def json_response(status: int, payload: Any, headers: dict[str, str] | None = None) -> Response:
    return Response(status, json.dumps(payload).encode("utf-8"), headers=headers or {})


class Service:
    """One ``AgentLoop``, the routes over it, and the photos held for review."""

    def __init__(
        self,
        *,
        loop: AgentLoop,
        upload_dir: Path,
        static_dir: Path,
        reviewer_token: str | None,
        max_held_photos: int = MAX_HELD_PHOTOS,
    ) -> None:
        self.loop = loop
        self.upload_dir = upload_dir
        self.static_dir = static_dir
        self._reviewer_token = reviewer_token or None
        self._max_held = max_held_photos
        self._held: OrderedDict[str, Path] = OrderedDict()
        self._held_lock = threading.Lock()

    def handle(
        self, method: str, path: str, body: bytes = b"", authorization: str | None = None
    ) -> Response:
        try:
            if method == "GET":
                return self._get(path, authorization)
            if method == "POST":
                if len(body) > MAX_BODY_BYTES:
                    raise RouteError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "payload_too_large")
                return self._post(path, body, authorization)
            raise RouteError(HTTPStatus.NOT_FOUND, "not_found")
        except RouteError as exc:
            return json_response(exc.status, {"error": exc.error}, exc.headers)
        except KeyError as exc:
            return json_response(HTTPStatus.NOT_FOUND, {"error": f"unknown capture_id: {exc}"})
        except (RuntimeError, PermissionError, ValueError) as exc:
            # The chokepoint's own refusals (wrong state, wrong actor, undecodable image).
            return json_response(HTTPStatus.CONFLICT, {"error": str(exc)})
        except Exception as exc:  # boundary of last resort: never a bare socket hang
            return json_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    # ---- routing ------------------------------------------------------------------------

    def _get(self, path: str, authorization: str | None) -> Response:
        if path == "/health":
            return json_response(HTTPStatus.OK, {"status": "ok"})
        if path in ("/", "/review"):
            html = (self.static_dir / "review.html").read_bytes()
            return Response(HTTPStatus.OK, html, "text/html; charset=utf-8")
        if path == "/pending":
            captures = list(self.loop.captures.values())
            waiting = [capture_view(c) for c in captures if c.state == "escalated"]
            return json_response(HTTPStatus.OK, waiting)
        for prefix, tool in (("/capture/", "get_capture"), ("/trace/", "get_trace")):
            if path.startswith(prefix):
                capture_id = self._known(path.removeprefix(prefix))
                result = invoke(tool, {"capture_id": capture_id}, "agent", loop=self.loop)
                return json_response(HTTPStatus.OK, result)
        if path.startswith("/overlay/"):
            return self._overlay(path.removeprefix("/overlay/"), authorization)
        raise RouteError(HTTPStatus.NOT_FOUND, "not_found")

    def _post(self, path: str, body: bytes, authorization: str | None) -> Response:
        if path == "/inspect":
            return self._receive(body, successor_id=None)
        if path.startswith("/retake/"):
            return self._receive(body, successor_id=self._known(path.removeprefix("/retake/")))
        for verb in REVIEWER_VERBS:
            prefix = f"/{verb}/"
            if path.startswith(prefix):
                return self._review(verb, path.removeprefix(prefix), body, authorization)
        raise RouteError(HTTPStatus.NOT_FOUND, "not_found")

    # ---- routes -------------------------------------------------------------------------

    def _receive(self, body: bytes, *, successor_id: str | None) -> Response:
        """A photo arrives: a new capture (``/inspect``) or the retake a capture was asked
        for (``/retake/<successor_id>``). Either way the same loop driver runs on it."""
        if not body:
            raise RouteError(HTTPStatus.BAD_REQUEST, "empty body: post raw image bytes")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        photo = self.upload_dir / f"{uuid.uuid4().hex}.jpg"
        photo.write_bytes(body)
        try:
            if successor_id is None:
                capture_id = self.loop.open_capture(photo)
            else:
                self.loop.attach_image(successor_id, photo)
                capture_id = successor_id
            # The same driver tools/run_demo.py calls: the verdict picks the next invoke().
            cap = process_capture(capture_id, loop=self.loop)
        except BaseException:
            photo.unlink(missing_ok=True)
            raise
        if cap.state == "escalated":
            self._hold(capture_id, photo)
        else:
            photo.unlink(missing_ok=True)
        return json_response(HTTPStatus.OK, capture_view(cap))

    def _review(
        self, verb: str, capture_id: str, body: bytes, authorization: str | None
    ) -> Response:
        self._require_reviewer(authorization)
        capture_id = self._known(capture_id)
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise RouteError(HTTPStatus.BAD_REQUEST, f"body is not JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RouteError(HTTPStatus.BAD_REQUEST, "body must be a JSON object")
        note = payload.get("note")
        if note is not None and not isinstance(note, str):
            raise RouteError(HTTPStatus.BAD_REQUEST, "note must be a string")
        args: dict[str, Any] = {"capture_id": capture_id, "note": note}
        if verb == "resolve_duplicate":
            is_duplicate = payload.get("is_duplicate")
            if not isinstance(is_duplicate, bool):
                raise RouteError(HTTPStatus.BAD_REQUEST, "is_duplicate must be true or false")
            args["is_duplicate"] = is_duplicate
        # The SAME invoke() the agent's tools go through; actor="reviewer" is the only
        # difference, and the token check above is what entitles this request to it.
        invoke(verb, args, "reviewer", loop=self.loop)
        cap = self.loop.captures[capture_id]
        if cap.state != "escalated":
            self._release(capture_id)
        return json_response(HTTPStatus.OK, capture_view(cap))

    def _overlay(self, capture_id: str, authorization: str | None) -> Response:
        self._require_reviewer(authorization)
        cap = self.loop.captures[self._known(capture_id)]
        with self._held_lock:
            photo = self._held.get(capture_id)
        if photo is None or not photo.exists() or cap.measurements is None:
            raise RouteError(
                HTTPStatus.GONE,
                "photo not held: only an escalated capture's photo is kept, "
                "and only until the reviewer decides",
            )
        image = overlay.render_jpeg(photo, cap.measurements, cap.verdict)
        return Response(HTTPStatus.OK, image, "image/jpeg", {"Cache-Control": "no-store"})

    # ---- helpers ------------------------------------------------------------------------

    def _known(self, capture_id: str) -> str:
        if capture_id not in self.loop.captures:
            raise RouteError(HTTPStatus.NOT_FOUND, f"unknown capture_id: {capture_id}")
        return capture_id

    def _require_reviewer(self, authorization: str | None) -> None:
        if self._reviewer_token is None:
            raise RouteError(
                HTTPStatus.UNAUTHORIZED,
                "reviewer routes are closed: no reviewer token is configured",
                _BEARER_CHALLENGE,
            )
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            token.strip().encode("utf-8"), self._reviewer_token.encode("utf-8")
        ):
            raise RouteError(HTTPStatus.UNAUTHORIZED, "reviewer token required", _BEARER_CHALLENGE)

    def _hold(self, capture_id: str, photo: Path) -> None:
        with self._held_lock:
            self._held[capture_id] = photo
            while len(self._held) > self._max_held:
                _, oldest = self._held.popitem(last=False)
                oldest.unlink(missing_ok=True)

    def _release(self, capture_id: str) -> None:
        with self._held_lock:
            photo = self._held.pop(capture_id, None)
        if photo is not None:
            photo.unlink(missing_ok=True)

    def held_photo_count(self) -> int:
        with self._held_lock:
            return len(self._held)
