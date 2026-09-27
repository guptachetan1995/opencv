#!/usr/bin/env python3
"""Local, Docker-free, AWS-free smoke check for deploy/handler.py.

Calls ``handler.handler()`` in-process with two fake Lambda Function URL events. Catches a
broken import or a routing bug before anyone spends a Docker build or a real deploy on it.

    python3 deploy/smoke_local.py

Exits 0 only if both calls return the expected shape.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent
ENTRY = DEPLOY_DIR.parent
for p in (ENTRY / "src", DEPLOY_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import handler as lambda_handler  # noqa: E402

SAMPLE_IMAGE = ENTRY / "data" / "synthetic" / "clean_a.jpg"


def _get(path: str) -> dict:
    event = {"requestContext": {"http": {"method": "GET"}}, "rawPath": path}
    return lambda_handler.handler(event, None)


def _post(path: str, body: bytes) -> dict:
    event = {
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": path,
        "body": base64.b64encode(body).decode("ascii"),
        "isBase64Encoded": True,
    }
    return lambda_handler.handler(event, None)


def main() -> int:
    if not SAMPLE_IMAGE.exists():
        print(f"smoke: missing sample image {SAMPLE_IMAGE}", file=sys.stderr)
        return 1

    health = _get("/health")
    if health["statusCode"] != 200:
        print(f"smoke: /health returned {health}", file=sys.stderr)
        return 1
    print("GET /health ->", health)

    inspect = _post("/inspect", SAMPLE_IMAGE.read_bytes())
    if inspect["statusCode"] != 200:
        print(f"smoke: /inspect returned {inspect}", file=sys.stderr)
        return 1
    print("POST /inspect -> verdict:", json.loads(inspect["body"]).get("verdict"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
