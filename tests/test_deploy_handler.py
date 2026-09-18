"""deploy/handler.py — the actual Lambda entry point (SPEC §9/§12, #46/#47). This file had
no dedicated coverage at all before this suite; the fixes below (the /approve size cap and
the per-request temp-file cleanup) mirror app/server.py's own but are unique code here, so
they need their own tests rather than relying on app/server.py's suite to stand in for them.

Each test resets the module-level ``_loop`` singleton first (mirroring a fresh Lambda
execution environment) so tests don't see each other's captures.
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
from secondlook.agent_loop import AgentLoop  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(handler, "_loop", AgentLoop())
    monkeypatch.setattr(handler, "UPLOAD_DIR", tmp_path / "uploads")
    yield


def _post_event(path: str, body: bytes, *, is_base64: bool = True) -> dict:
    return {
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": path,
        "isBase64Encoded": is_base64,
        "body": base64.b64encode(body).decode("ascii") if is_base64 else body.decode("utf-8"),
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
    oversized = b"x" * (handler.MAX_BODY_BYTES + 1)
    response = handler.handler(_post_event("/inspect", oversized), None)
    assert response["statusCode"] == 413


def test_oversized_approve_body_is_413():
    """/approve previously had no size cap at all -- only /inspect did."""
    response = handler.handler(_inspect_event("not_doc"), None)
    capture_id = json.loads(response["body"])["capture_id"]
    oversized = b"x" * (handler.MAX_BODY_BYTES + 1)
    response = handler.handler(_post_event(f"/approve/{capture_id}", oversized), None)
    assert response["statusCode"] == 413


def test_malformed_upload_is_409_not_500():
    response = handler.handler(_post_event("/inspect", b"not a jpeg at all"), None)
    assert response["statusCode"] == 409
    assert "could not decode" in json.loads(response["body"])["error"]


def test_uploaded_file_does_not_survive_the_request():
    """A warm Lambda execution environment persists across many invocations with no
    shutdown hook to clean up after itself -- leaving the file behind would accumulate
    one per invocation in /tmp until the environment recycles."""
    response = handler.handler(_inspect_event("clean_a"), None)
    assert response["statusCode"] == 200
    assert list(handler.UPLOAD_DIR.iterdir()) == []
