#!/usr/bin/env python3
"""Smoke command for the HTTP serving layer.

Starts its own copy of the server, waits for it to become healthy, hits ``GET /health``
and one ``POST /inspect`` against a real committed dataset image, prints the decision, and
shuts the server back down.

    python3 app/smoke.py

Exits 0 only if both calls succeed and a verdict comes back. Only ever talks to
``127.0.0.1``: no network, no AWS, no credential.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ENTRY = APP_DIR.parent
if str(ENTRY) not in sys.path:
    sys.path.insert(0, str(ENTRY))

from app.server import SecondLookServer  # noqa: E402

HOST = "127.0.0.1"
PORT = 8099  # dedicated to the smoke run, distinct from server.py's default 8080
SAMPLE_IMAGE = ENTRY / "data" / "synthetic" / "clean_a.jpg"


def _wait_until_healthy(base_url: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError) as exc:
            last_error = exc
        time.sleep(0.05)
    raise RuntimeError(f"server never became healthy: {last_error}")


def main() -> int:
    if not SAMPLE_IMAGE.exists():
        print(f"smoke: missing sample image {SAMPLE_IMAGE}", file=sys.stderr)
        return 1

    server = SecondLookServer((HOST, PORT))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{HOST}:{PORT}"
    try:
        _wait_until_healthy(base_url)

        with urllib.request.urlopen(f"{base_url}/health", timeout=2) as resp:
            health = json.loads(resp.read())
        print(f"GET /health -> {resp.status} {health}")
        if health.get("status") != "ok":
            raise RuntimeError(f"unexpected /health body: {health}")

        request = urllib.request.Request(
            f"{base_url}/inspect",
            data=SAMPLE_IMAGE.read_bytes(),
            method="POST",
            headers={"Content-Type": "image/jpeg"},
        )
        with urllib.request.urlopen(request, timeout=10) as resp:
            result = json.loads(resp.read())
        verdict = result.get("verdict")
        if verdict is None:
            raise RuntimeError(f"inspect returned no verdict: {result}")
        print(
            f"POST /inspect {SAMPLE_IMAGE.name} -> state={result['state']} "
            f"verdict={verdict['outcome']} ({verdict['rule_id']}): {verdict['reason_text']}"
        )
        print("smoke: ok")
        return 0
    except Exception as exc:  # print the failure before the finally block tears down
        print(f"smoke: FAILED — {exc}", file=sys.stderr)
        return 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
