"""A stdio MCP server over the agent's own tools — and nothing else.

Lets any MCP client (an LLM agent) drive Second Look's perception-decision-action loop
through exactly the calls ``process_capture`` makes. Every agent tool and read below is
``agent_loop.invoke(tool, args, actor="agent")``, the same chokepoint the HTTP routes and
the review page use, and ``run_loop`` is ``process_capture``, which only calls ``invoke``.
The two exceptions decide nothing: ``open_capture`` and ``attach_retake`` put a photo into
a slot through ``AgentLoop.open_capture`` and ``AgentLoop.attach_image``, the same
photo-arrival plumbing HTTP ``POST /inspect`` and ``POST /retake`` call, outside ``invoke``
there too. ``attach_image`` only fills an open, unmeasured retake slot.

The human-only verbs (``approve``, ``reject``, ``resolve_duplicate``) are not listed and
cannot be called: an unknown tool name is refused here, and ``invoke`` would refuse
``actor="agent"`` for them anyway. Each agent tool also refuses a capture that has left the
agent's part of the lifecycle (escalated, awaiting a retake, or decided).

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout (the MCP stdio transport).
Standard library only; nothing but protocol messages is ever written to stdout.

    .venv/bin/python app/mcp_server.py

Client configuration (absolute paths): command ``<repo>/.venv/bin/python``, args
``["<repo>/app/mcp_server.py"]``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ENTRY = Path(__file__).resolve().parent.parent
if str(ENTRY / "src") not in sys.path:
    sys.path.insert(0, str(ENTRY / "src"))

from secondlook.agent_loop import AgentLoop, capture_view, invoke, process_capture  # noqa: E402

SERVER_INFO = {"name": "second-look", "version": "0.1.0"}
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "Second Look inspects receipt photos with OpenCV 5. Open a capture from a local image "
    "file, then either run_loop (the deterministic loop picks the next call from the "
    "measurements) or call inspect_capture, decide_capture and the action the verdict names. "
    "You can never accept a capture a person has to see: approve, reject and "
    "resolve_duplicate are human-only and not offered here."
)

_CAPTURE_ID = {"capture_id": {"type": "string", "description": "A capture id such as c_001."}}

TOOLS: dict[str, dict[str, Any]] = {
    "open_capture": {
        "description": (
            "Open a new capture from a local image file (JPEG or PNG) and return its "
            "capture_id. Does not measure, decide or accept anything; the capture starts in "
            "state 'received'. Does not upload or copy the file anywhere."
        ),
        "properties": {"image_path": {"type": "string", "description": "Absolute file path."}},
        "required": ["image_path"],
    },
    "attach_retake": {
        "description": (
            "Attach the retake photo to the successor slot that request_recapture opened "
            "(the capture_id it returned). Does not measure or decide it; call run_loop or "
            "compare_captures next. Refused for any capture that is not an open, "
            "unmeasured retake slot, so a photo can never be swapped under a measured one."
        ),
        "properties": {
            **_CAPTURE_ID,
            "image_path": {"type": "string", "description": "Absolute file path."},
        },
        "required": ["capture_id", "image_path"],
    },
    "run_loop": {
        "description": (
            "Run the deterministic loop on a 'received' capture: compare against its parent "
            "if it is a retake, inspect, decide, then request a retake or escalate as the "
            "verdict says. Returns the capture. Does nothing to a capture that is not "
            "'received'. Never approves an escalated capture; a person must."
        ),
        "properties": _CAPTURE_ID,
        "required": ["capture_id"],
    },
    "inspect_capture": {
        "description": (
            "Run the eight OpenCV 5 measurements on the capture's photo and store the "
            "record. Does not decide a verdict, request a retake or accept anything. "
            "Refused unless the capture is 'received' or 'measured'."
        ),
        "properties": _CAPTURE_ID,
        "required": ["capture_id"],
    },
    "decide_capture": {
        "description": (
            "Evaluate the committed rule cascade on the stored measurements and record the "
            "verdict (accept, retake or escalate) with every clause evaluated. An 'accept' "
            "verdict accepts the capture; the cascade cannot accept a suspected duplicate. "
            "Does not re-run OpenCV. Refused unless the capture is 'received' or 'measured', "
            "so it cannot re-decide an escalated or accepted capture."
        ),
        "properties": _CAPTURE_ID,
        "required": ["capture_id"],
    },
    "request_recapture": {
        "description": (
            "Ask for a retake of a capture whose verdict is 'retake': records the failing "
            "metric and hint box the verdict names and opens a successor slot (returned). "
            "Does not notify anyone and does not delete the old capture. Refused for any "
            "capture whose own verdict is not 'retake'."
        ),
        "properties": {
            **_CAPTURE_ID,
            "failing_metric": {
                "type": "string",
                "description": "Optional; must match the metric the verdict failed on.",
            },
        },
        "required": ["capture_id"],
    },
    "compare_captures": {
        "description": (
            "Measure a retake photo and report whether the metric that failed on the "
            "previous capture is now fixed, unchanged or worse. Does not decide a verdict "
            "or store measurements on the retake. Refused unless new_id is the unmeasured "
            "retake slot of previous_id."
        ),
        "properties": {
            "previous_id": {"type": "string", "description": "The capture that was retaken."},
            "new_id": {"type": "string", "description": "Its successor slot."},
        },
        "required": ["previous_id", "new_id"],
    },
    "escalate": {
        "description": (
            "Put a capture whose verdict is 'escalate' in the human review queue, under the "
            "verdict's own reason code. Does not approve or reject anything, and after it no "
            "agent tool can move the capture again; only a person can. Refused for any "
            "capture whose own verdict is not 'escalate', and a reason that differs from the "
            "verdict's is refused, not recorded: it cannot relabel a suspected duplicate."
        ),
        "properties": {
            **_CAPTURE_ID,
            "reason": {
                "type": "string",
                "description": "Optional; must match the verdict's reason_code.",
            },
        },
        "required": ["capture_id"],
    },
    "get_capture": {
        "description": (
            "Read one capture: state, verdict, measurements, and the successor slot if a "
            "retake was requested. Changes nothing and returns a copy, never the live record."
        ),
        "properties": _CAPTURE_ID,
        "required": ["capture_id"],
    },
    "get_trace": {
        "description": (
            "Read the capture's trace across its whole retake chain: every call, its actor, "
            "inputs, outputs and the entry that caused it. Does not change anything."
        ),
        "properties": _CAPTURE_ID,
        "required": ["capture_id"],
    },
}


class McpServer:
    def __init__(self, loop: AgentLoop | None = None) -> None:
        self.loop = loop or AgentLoop()

    def handle(self, message: Any) -> dict[str, Any] | None:
        """One JSON-RPC message in, one response out (None for a notification). A batch
        (a JSON array) or any other non-object is answered as an invalid request: MCP
        dropped JSON-RPC batching in 2025-06-18, and this server never supported it."""
        if not isinstance(message, dict):
            return _error(None, -32600, "Invalid Request: expected one JSON-RPC object")
        method = message.get("method")
        msg_id = message.get("id")
        if msg_id is None:
            return None  # notifications (notifications/initialized, cancelled) need no reply
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return _error(msg_id, -32602, "Invalid params: expected an object")
        if method == "initialize":
            requested = params.get("protocolVersion")
            version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return _result(
                msg_id,
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                    "instructions": INSTRUCTIONS,
                },
            )
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": [_describe(n, t) for n, t in TOOLS.items()]})
        if method == "tools/call":
            name = params.get("name")
            if name not in TOOLS:
                return _error(msg_id, -32602, f"Unknown tool: {name}")
            try:
                output = self._call(name, params.get("arguments") or {})
            except (KeyError, RuntimeError, PermissionError, ValueError, TypeError) as exc:
                text = f"{type(exc).__name__}: {exc}"
                return _result(
                    msg_id, {"content": [{"type": "text", "text": text}], "isError": True}
                )
            payload = json.dumps(output)
            return _result(
                msg_id,
                {
                    "content": [{"type": "text", "text": payload}],
                    "structuredContent": {"result": output},
                    "isError": False,
                },
            )
        return _error(msg_id, -32601, f"Method not found: {method}")

    def _call(self, name: str, args: dict[str, Any]) -> Any:
        if name == "open_capture":
            path = Path(args["image_path"])
            if not path.is_file():
                raise ValueError(f"no such file: {path}")
            return {"capture_id": self.loop.open_capture(path)}
        if name == "attach_retake":
            path = Path(args["image_path"])
            if not path.is_file():
                raise ValueError(f"no such file: {path}")
            self.loop.attach_image(args["capture_id"], path)
            return {"capture_id": args["capture_id"], "state": "received"}
        if name == "run_loop":
            return capture_view(process_capture(args["capture_id"], loop=self.loop))
        result = invoke(name, args, "agent", loop=self.loop)
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return result


def _describe(name: str, tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": tool["description"],
        "inputSchema": {
            "type": "object",
            "properties": tool["properties"],
            "required": tool["required"],
            "additionalProperties": False,
        },
    }


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def main() -> int:
    server = McpServer()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            reply: dict[str, Any] | None = _error(None, -32700, f"Parse error: {exc}")
        else:
            reply = server.handle(message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
