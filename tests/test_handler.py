"""The HTTP serving layer: each promised behaviour as one test.

Every test drives a real `SecondLookServer` on an ephemeral local port with the standard
library's `urllib.request` as the client — no new dev dependency, no network beyond
127.0.0.1, no AWS, no credential.
"""

from __future__ import annotations

import json
import sys
import tempfile
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
from secondlook.agent_loop import AgentLoop  # noqa: E402
from secondlook.service import Service  # noqa: E402

TOKEN = "test-reviewer-token"
REVIEWER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def running_server() -> Iterator[SecondLookServer]:
    server = SecondLookServer(("127.0.0.1", 0), reviewer_token=TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def live_server(running_server: SecondLookServer) -> str:
    return f"http://127.0.0.1:{running_server.server_address[1]}"


def _get(
    base_url: str, path: str, headers: dict[str, str] | None = None
) -> tuple[int, dict | list]:
    request = urllib.request.Request(f"{base_url}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(
    base_url: str,
    path: str,
    body: bytes,
    content_type: str,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": content_type, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _inspect(base_url: str, sample: str, path: str = "/inspect") -> tuple[int, dict]:
    image = (DATA / f"{sample}.jpg").read_bytes()
    return _post(base_url, path, image, "image/jpeg")


def _review(
    base_url: str, verb: str, capture_id: str, payload: dict, headers: dict | None = REVIEWER
) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    return _post(base_url, f"/{verb}/{capture_id}", body, "application/json", headers)


def _approve(base_url: str, capture_id: str, note: str | None = None) -> tuple[int, dict]:
    return _review(base_url, "approve", capture_id, {"note": note})


# ---- GET /health --------------------------------------------------------------------


def test_health(live_server: str) -> None:
    status, body = _get(live_server, "/health")
    assert status == HTTPStatus.OK
    assert body == {"status": "ok"}


# ---- inspect -> escalate -> approve -> resume --------------------------------------------


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
    status, body = _post(
        live_server, f"/approve/{capture_id}", oversized, "application/json", REVIEWER
    )
    assert status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert body["error"] == "payload_too_large"


# ---- the reviewer is authenticated, not just named -------------------------------------


@pytest.mark.parametrize("verb", ["approve", "reject", "resolve_duplicate"])
@pytest.mark.parametrize(
    "headers",
    [None, {"Authorization": "Bearer wrong-token"}, {"Authorization": TOKEN}],
    ids=["no-token", "wrong-token", "no-bearer-scheme"],
)
def test_reviewer_routes_refuse_without_the_token(
    live_server: str, verb: str, headers: dict | None
) -> None:
    status, result = _inspect(live_server, "not_doc")
    capture_id = result["capture_id"]
    payload = {"note": "x", "is_duplicate": False}
    status, body = _review(live_server, verb, capture_id, payload, headers)
    assert status == HTTPStatus.UNAUTHORIZED
    assert "token" in body["error"]
    status, capture = _get(live_server, f"/capture/{capture_id}")
    assert capture["state"] == "escalated"  # refused before invoke() was ever called


def test_reviewer_routes_are_closed_when_no_token_is_configured() -> None:
    from secondlook.agent_loop import AgentLoop
    from secondlook.service import Service

    service = Service(
        loop=AgentLoop(),
        upload_dir=Path(tempfile.mkdtemp()),
        static_dir=ENTRY / "app" / "static",
        reviewer_token=None,
    )
    result = service.handle("POST", "/inspect", (DATA / "not_doc.jpg").read_bytes())
    capture_id = json.loads(result.body)["capture_id"]
    refused = service.handle("POST", f"/approve/{capture_id}", b"{}", "Bearer anything")
    assert refused.status == HTTPStatus.UNAUTHORIZED
    assert service.loop.captures[capture_id].state == "escalated"


# ---- reject and the two-step duplicate resolution, over HTTP ---------------------------


def test_reject_over_http(live_server: str) -> None:
    status, result = _inspect(live_server, "not_doc")
    capture_id = result["capture_id"]
    status, rejected = _review(live_server, "reject", capture_id, {"note": "not a receipt"})
    assert status == HTTPStatus.OK
    assert rejected["state"] == "rejected"
    status, trace = _get(live_server, f"/trace/{capture_id}")
    assert (trace[-1]["actor"], trace[-1]["action"]) == ("reviewer", "reject")


def test_duplicate_resolve_then_approve_over_http(live_server: str) -> None:
    _inspect(live_server, "clean_a")
    status, dup = _inspect(live_server, "dup_a")
    assert dup["review_reason"] == "suspected_duplicate"
    capture_id = dup["capture_id"]

    status, body = _approve(live_server, capture_id)
    assert status == HTTPStatus.CONFLICT  # approve refuses an unresolved duplicate

    status, body = _review(live_server, "resolve_duplicate", capture_id, {"is_duplicate": "no"})
    assert status == HTTPStatus.BAD_REQUEST  # is_duplicate must be a real boolean

    status, cleared = _review(
        live_server,
        "resolve_duplicate",
        capture_id,
        {"is_duplicate": False, "note": "two lunches"},
    )
    assert status == HTTPStatus.OK
    assert (cleared["state"], cleared["duplicate_resolved"]) == ("escalated", True)

    status, approved = _approve(live_server, capture_id, note="checked")
    assert status == HTTPStatus.OK
    assert approved["state"] == "accepted"


def test_confirmed_duplicate_is_rejected_over_http(live_server: str) -> None:
    _inspect(live_server, "clean_a")
    status, dup = _inspect(live_server, "dup_a")
    status, result = _review(
        live_server, "resolve_duplicate", dup["capture_id"], {"is_duplicate": True}
    )
    assert status == HTTPStatus.OK
    assert result["state"] == "rejected"


# ---- the retake loop over HTTP ---------------------------------------------------------


def test_retake_route_runs_the_chain_over_http(live_server: str) -> None:
    """The qualifying beat, over HTTP: glare -> retake slot -> the retake posted to it fires
    a different rule on a different metric, and the trace links the two captures."""
    status, first = _inspect(live_server, "glare_text")
    assert (first["state"], first["verdict"]["rule_id"]) == ("awaiting_retake", "glare_over_total")
    successor_id = first["successor_id"]
    assert successor_id is not None

    status, second = _inspect(live_server, "crop_bottom", path=f"/retake/{successor_id}")
    assert status == HTTPStatus.OK
    assert second["capture_id"] == successor_id
    assert (second["parent_id"], second["attempt"]) == (first["capture_id"], 2)
    assert second["verdict"]["rule_id"] == "bottom_edge_clipped"

    status, trace = _get(live_server, f"/trace/{successor_id}")
    compare = next(row for row in trace if row["action"] == "compare_captures")
    assert compare["inputs"]["metric"] == "glare_over_text_frac"
    assert compare["outputs"]["status"] == "fixed"
    request = next(row for row in trace if row["action"] == "request_recapture")
    assert compare["caused_by"] == request["seq"]

    status, third = _inspect(live_server, "clean_a", path=f"/retake/{second['successor_id']}")
    assert (third["state"], third["attempt"]) == ("accepted", 3)


def test_retake_route_refuses_a_capture_that_is_not_an_open_slot(live_server: str) -> None:
    status, first = _inspect(live_server, "not_doc")
    status, body = _inspect(live_server, "clean_a", path=f"/retake/{first['capture_id']}")
    assert status == HTTPStatus.CONFLICT
    status, body = _inspect(live_server, "clean_a", path="/retake/c_999")
    assert status == HTTPStatus.NOT_FOUND


# ---- the evidence overlay --------------------------------------------------------------


def _get_bytes(base_url: str, path: str, headers: dict | None = None) -> tuple[int, str, bytes]:
    request = urllib.request.Request(f"{base_url}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            return resp.status, resp.headers.get("Content-Type"), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type"), exc.read()


def test_overlay_is_reviewer_only_and_drawn_while_the_photo_is_held(
    running_server: SecondLookServer, live_server: str
) -> None:
    status, result = _inspect(live_server, "not_doc")
    capture_id = result["capture_id"]
    assert running_server.service.held_photo_count() == 1  # held for the reviewer

    status, _, _ = _get_bytes(live_server, f"/overlay/{capture_id}")
    assert status == HTTPStatus.UNAUTHORIZED

    status, content_type, image = _get_bytes(live_server, f"/overlay/{capture_id}", REVIEWER)
    assert status == HTTPStatus.OK
    assert content_type == "image/jpeg"
    assert image[:3] == b"\xff\xd8\xff"

    _review(live_server, "reject", capture_id, {"note": "not a receipt"})
    assert running_server.service.held_photo_count() == 0  # deleted once decided
    assert list(running_server._upload_dir.iterdir()) == []
    status, _, _ = _get_bytes(live_server, f"/overlay/{capture_id}", REVIEWER)
    assert status == HTTPStatus.GONE


def test_malformed_upload_is_409_not_500(
    running_server: SecondLookServer, live_server: str
) -> None:
    status, body = _post(live_server, "/inspect", b"not a jpeg at all", "image/jpeg")
    assert status == HTTPStatus.CONFLICT
    assert "could not decode" in body["error"]
    # the refusal names no server path: not the upload directory, not the temp file
    assert str(running_server._upload_dir) not in body["error"]
    assert "/" not in body["error"]


def test_held_photos_past_the_cap_are_deleted_oldest_first(tmp_path: Path) -> None:
    """The documented cap: at most max_held_photos escalated photos are kept for the
    reviewer; past it the oldest is deleted from disk and its overlay answers 410."""
    service = Service(
        loop=AgentLoop(),
        upload_dir=tmp_path,
        static_dir=ENTRY / "app" / "static",
        reviewer_token=TOKEN,
        max_held_photos=2,
    )
    ids = []
    for _ in range(3):
        response = service.handle("POST", "/inspect", (DATA / "not_doc.jpg").read_bytes())
        body = json.loads(response.body)
        assert (response.status, body["state"]) == (HTTPStatus.OK, "escalated")
        ids.append(body["capture_id"])
    auth = f"Bearer {TOKEN}"
    statuses = [service.handle("GET", f"/overlay/{i}", authorization=auth).status for i in ids]
    assert statuses == [HTTPStatus.GONE, HTTPStatus.OK, HTTPStatus.OK]
    assert service.held_photo_count() == 2
    assert len(list(tmp_path.iterdir())) == 2


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
    for route in ("/approve/", "/reject/", "/resolve_duplicate/", "/overlay/", "/pending"):
        assert route in html  # the page's buttons hit the same routes the tests do
    assert "Authorization" in html
    assert "innerHTML" not in html  # cards are built with textContent, never markup
