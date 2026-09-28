"""deploy/handler.py — the actual Lambda entry point. The routes live in
``secondlook.service`` (shared with app/server.py); what is unique here is the translation
between a Function URL event and that service — the base64 body, the lowercase headers,
the base64 binary response — so it is tested through real event dicts, not by trusting
app/server.py's suite to stand in for it.

Each test swaps in a fresh module-level service first (mirroring a fresh Lambda execution
environment) so tests don't see each other's captures.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

ENTRY = Path(__file__).resolve().parent.parent
if str(ENTRY) not in sys.path:
    sys.path.insert(0, str(ENTRY))

import deploy.handler as handler  # noqa: E402

from conftest import DATA  # noqa: E402
from secondlook.service import MAX_BODY_BYTES  # noqa: E402

TOKEN = "lambda-test-token"


@pytest.fixture(autouse=True)
def fresh_service(tmp_path, monkeypatch):
    service = handler.make_service(upload_dir=tmp_path / "uploads", reviewer_token=TOKEN)
    monkeypatch.setattr(handler, "_service", service)
    yield service


def _post_event(
    path: str, body: bytes, *, is_base64: bool = True, token: str | None = TOKEN
) -> dict:
    return {
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": path,
        "headers": {"authorization": f"Bearer {token}"} if token else {},
        "isBase64Encoded": is_base64,
        "body": base64.b64encode(body).decode("ascii") if is_base64 else body.decode("utf-8"),
    }


def _get_event(path: str, token: str | None = None) -> dict:
    return {
        "requestContext": {"http": {"method": "GET"}},
        "rawPath": path,
        "headers": {"authorization": f"Bearer {token}"} if token else {},
    }


def _inspect_event(sample: str) -> dict:
    return _post_event("/inspect", (DATA / f"{sample}.jpg").read_bytes())


def test_inspect_then_approve_round_trip():
    response = handler.handler(_inspect_event("not_doc"), None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["state"] == "escalated"

    approve_body = json.dumps({"note": "checked"}).encode("utf-8")
    response = handler.handler(_post_event(f"/approve/{body['capture_id']}", approve_body), None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["state"] == "accepted"


def test_oversized_inspect_body_is_413():
    oversized = b"x" * (MAX_BODY_BYTES + 1)
    response = handler.handler(_post_event("/inspect", oversized), None)
    assert response["statusCode"] == 413


def test_oversized_approve_body_is_413():
    """/approve previously had no size cap at all -- only /inspect did."""
    response = handler.handler(_inspect_event("not_doc"), None)
    capture_id = json.loads(response["body"])["capture_id"]
    oversized = b"x" * (MAX_BODY_BYTES + 1)
    response = handler.handler(_post_event(f"/approve/{capture_id}", oversized), None)
    assert response["statusCode"] == 413


def test_malformed_upload_is_409_not_500():
    response = handler.handler(_post_event("/inspect", b"not a jpeg at all"), None)
    assert response["statusCode"] == 409
    assert "could not decode" in json.loads(response["body"])["error"]


def test_uploaded_file_does_not_survive_the_request(fresh_service):
    """A warm Lambda execution environment persists across many invocations with no
    shutdown hook to clean up after itself -- leaving the file behind would accumulate
    one per invocation in /tmp until the environment recycles."""
    response = handler.handler(_inspect_event("clean_a"), None)
    assert response["statusCode"] == 200
    assert list(fresh_service.upload_dir.iterdir()) == []


def test_approve_without_the_reviewer_token_is_401():
    """A Function URL with auth-type NONE is public; the reviewer token is what keeps
    /approve from being anyone's."""
    response = handler.handler(_inspect_event("not_doc"), None)
    capture_id = json.loads(response["body"])["capture_id"]
    body = json.dumps({"note": "x"}).encode("utf-8")
    for token in (None, "wrong"):
        refused = handler.handler(_post_event(f"/approve/{capture_id}", body, token=token), None)
        assert refused["statusCode"] == 401
    trace = json.loads(handler.handler(_get_event(f"/trace/{capture_id}"), None)["body"])
    assert [row["action"] for row in trace] == ["inspect_capture", "decide_capture", "escalate"]


def test_reviewer_routes_closed_when_no_token_is_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(handler, "_service", handler.make_service(upload_dir=tmp_path / "u"))
    response = handler.handler(_inspect_event("not_doc"), None)
    capture_id = json.loads(response["body"])["capture_id"]
    refused = handler.handler(_post_event(f"/reject/{capture_id}", b"{}"), None)
    assert refused["statusCode"] == 401


def test_overlay_is_returned_base64_encoded():
    response = handler.handler(_inspect_event("not_doc"), None)
    capture_id = json.loads(response["body"])["capture_id"]
    overlay = handler.handler(_get_event(f"/overlay/{capture_id}", token=TOKEN), None)
    assert overlay["statusCode"] == 200
    assert overlay["isBase64Encoded"] is True
    assert overlay["headers"]["Content-Type"] == "image/jpeg"
    assert base64.b64decode(overlay["body"])[:3] == b"\xff\xd8\xff"


def test_retake_route_through_the_lambda_event_shape():
    first = json.loads(handler.handler(_inspect_event("glare_text"), None)["body"])
    retake_event = _post_event(
        f"/retake/{first['successor_id']}", (DATA / "crop_bottom.jpg").read_bytes()
    )
    second = json.loads(handler.handler(retake_event, None)["body"])
    assert second["verdict"]["rule_id"] == "bottom_edge_clipped"
    assert second["parent_id"] == first["capture_id"]
