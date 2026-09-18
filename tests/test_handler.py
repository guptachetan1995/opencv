"""The HTTP serving layer (#63): the issue's own Definition of Done, each as one test.

Every test drives a real `SecondLookServer` on an ephemeral local port with the standard
library's `urllib.request` as the client — no new dev dependency, no network beyond
127.0.0.1, no AWS, no credential.
"""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path

import pytest

ENTRY = Path(__file__).resolve().parent.parent
if str(ENTRY) not in sys.path:
    sys.path.insert(0, str(ENTRY))

from app.server import SecondLookServer  # noqa: E402

from conftest import DATA  # noqa: E402


@pytest.fixture
def live_server() -> Iterator[str]:
    server = SecondLookServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get(base_url: str, path: str) -> tuple[int, dict | list]:
    try:
        with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(base_url: str, path: str, body: bytes, content_type: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{base_url}{path}", data=body, method="POST", headers={"Content-Type": content_type}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _inspect(base_url: str, sample: str) -> tuple[int, dict]:
    image = (DATA / f"{sample}.jpg").read_bytes()
    return _post(base_url, "/inspect", image, "image/jpeg")


def _approve(base_url: str, capture_id: str, note: str | None = None) -> tuple[int, dict]:
    body = json.dumps({"note": note}).encode("utf-8")
    return _post(base_url, f"/approve/{capture_id}", body, "application/json")


# ---- GET /health --------------------------------------------------------------------


def test_health(live_server: str) -> None:
    status, body = _get(live_server, "/health")
    assert status == HTTPStatus.OK
    assert body == {"status": "ok"}


# ---- the issue's own line: inspect -> escalate -> approve -> resume ------------------


def test_inspect_escalate_approve_resume_trace(live_server: str) -> None:
    status, result = _inspect(live_server, "not_doc")
    assert status == HTTPStatus.OK
    assert result["state"] == "escalated"
    assert result["verdict"]["outcome"] == "escalate"
    assert result["verdict"]["reason_code"] == "not_a_document"
    capture_id = result["capture_id"]

    status, pending = _get(live_server, "/pending")
    assert status == HTTPStatus.OK
    assert capture_id in {item["capture_id"] for item in pending}

    status, approved = _approve(live_server, capture_id, note="confirmed by reviewer")
    assert status == HTTPStatus.OK
    assert approved["state"] == "accepted"

    status, trace = _get(live_server, f"/trace/{capture_id}")
    assert status == HTTPStatus.OK
    actions = [row["action"] for row in trace]
    assert actions == ["inspect_capture", "decide_capture", "escalate", "approve"]
    escalate_entry = trace[2]
    approve_entry = trace[3]
    assert approve_entry["actor"] == "reviewer"
    assert approve_entry["caused_by"] == escalate_entry["seq"]

    # resumed: no longer waiting in the review queue
    status, pending_after = _get(live_server, "/pending")
    assert status == HTTPStatus.OK
    assert capture_id not in {item["capture_id"] for item in pending_after}


# ---- errors surface the chokepoint's own refusals, not a second mutation path --------


def test_unknown_capture_trace_is_404(live_server: str) -> None:
    status, body = _get(live_server, "/trace/does-not-exist")
    assert status == HTTPStatus.NOT_FOUND
    assert "error" in body


def test_approve_unescalated_capture_is_409(live_server: str) -> None:
    status, result = _inspect(live_server, "clean_a")
    assert status == HTTPStatus.OK
    assert result["state"] == "accepted"  # a clean capture auto-accepts, never escalates

    status, body = _approve(live_server, result["capture_id"])
    assert status == HTTPStatus.CONFLICT
    assert "error" in body


def test_oversized_payload_is_413(live_server: str) -> None:
    oversized = b"x" * (4 * 1024 * 1024 + 1)
    status, body = _post(live_server, "/inspect", oversized, "image/jpeg")
    assert status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert body["error"] == "payload_too_large"


def test_oversized_approve_body_is_413(live_server: str) -> None:
    """/approve previously had no size cap at all -- only /inspect did."""
    status, result = _inspect(live_server, "not_doc")
    capture_id = result["capture_id"]
    oversized = b"x" * (4 * 1024 * 1024 + 1)
    status, body = _post(live_server, f"/approve/{capture_id}", oversized, "application/json")
    assert status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert body["error"] == "payload_too_large"


def test_malformed_upload_is_409_not_500(live_server: str) -> None:
    status, body = _post(live_server, "/inspect", b"not a jpeg at all", "image/jpeg")
    assert status == HTTPStatus.CONFLICT
    assert "could not decode" in body["error"]


def test_uploaded_file_does_not_survive_the_request() -> None:
    """Each image is read once, inside process_capture; leaving it on disk afterward
    would accumulate one file per request for the life of the process. Built inline
    (rather than the live_server fixture) so the test can inspect the server's own
    upload directory, which the HTTP response never exposes by design."""
    server = SecondLookServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, _result = _inspect(base_url, "clean_a")
        assert status == HTTPStatus.OK
        assert list(server._upload_dir.iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_review_page_served_at_root(live_server: str) -> None:
    with urllib.request.urlopen(live_server, timeout=5) as resp:
        assert resp.status == HTTPStatus.OK
        html = resp.read().decode("utf-8")
    assert "/approve/" in html  # the approve button hits the same route the tests do
    assert "/pending" in html
