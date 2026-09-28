"""Lambda Function URL entry point for Second Look.

A thin adapter, like ``app/server.py``: it turns a Function URL event (payload format 2.0)
into one ``secondlook.service.Service.handle(...)`` call and the ``Response`` back into
the Lambda response shape. The routes, the reviewer-token check and the photo handling
all live in ``src/secondlook/service.py``, shared with ``app/server.py``.

Differs from ``app/server.py`` only where Lambda forces a difference:
  - Uploads go to ``/tmp`` (the only writable path in a Lambda execution environment).
  - No manual ``sys.path`` insert: the Dockerfile copies ``secondlook/`` directly under
    ``${LAMBDA_TASK_ROOT}``, already on the Lambda Python runtime's ``sys.path``.
  - The reviewer token comes only from the ``REVIEWER_TOKEN`` environment variable
    (``deploy/deploy.sh`` sets it); without one the reviewer routes stay closed.
  - A binary response (the overlay JPEG) is base64-encoded, as Function URLs require.
  - The module-level service persists only for one warm execution environment's
    lifetime; concurrent Lambda executions get independent, non-shared state. The planned
    S3-backed ``store.py`` (not built) is what would fix it.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from secondlook.agent_loop import AgentLoop
from secondlook.service import Response, Service

STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = Path("/tmp/secondlook-uploads")  # noqa: S108 -- the only writable Lambda path


def make_service(upload_dir: Path = UPLOAD_DIR, reviewer_token: str | None = None) -> Service:
    return Service(
        loop=AgentLoop(),
        upload_dir=upload_dir,
        static_dir=STATIC_DIR,
        reviewer_token=reviewer_token,
    )


_service = make_service(reviewer_token=os.environ.get("REVIEWER_TOKEN"))


def _decode_body(event: dict[str, Any]) -> bytes:
    raw = event.get("body") or ""
    return base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("utf-8")


def _authorization(event: dict[str, Any]) -> str | None:
    headers = event.get("headers") or {}
    return next((v for k, v in headers.items() if k.lower() == "authorization"), None)


def _to_lambda(response: Response) -> dict[str, Any]:
    textual = response.content_type.startswith(("application/json", "text/"))
    return {
        "statusCode": int(response.status),
        "headers": {"Content-Type": response.content_type, **response.headers},
        "body": response.body.decode("utf-8")
        if textual
        else base64.b64encode(response.body).decode("ascii"),
        "isBase64Encoded": not textual,
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """The Lambda entry point named by ``deploy/Dockerfile``'s ``CMD``. A Function URL event
    hands over the body already in memory, so the 4 MB guard runs inside the service (Lambda's
    own 6 MB synchronous payload cap is the backstop)."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    return _to_lambda(_service.handle(method, path, _decode_body(event), _authorization(event)))
