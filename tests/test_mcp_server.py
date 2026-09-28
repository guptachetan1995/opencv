"""The stdio MCP adapter: it offers the agent's tools and reads, never a human verb, and
every call it makes lands on the same invoke() chokepoint and state guards."""

from __future__ import annotations

import json
import re
import subprocess
import sys

from conftest import DATA, ENTRY
from secondlook.agent_loop import AGENT_TOOLS, HUMAN_VERBS, READ_TOOLS

sys.path.insert(0, str(ENTRY))

from app.mcp_server import TOOLS, McpServer  # noqa: E402


def _call(server: McpServer, name: str, arguments: dict, msg_id: int = 1) -> dict:
    reply = server.handle(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert reply is not None
    return reply


def _ok(reply: dict):
    assert reply["result"]["isError"] is False, reply
    return reply["result"]["structuredContent"]["result"]


def test_tool_list_is_the_agent_tools_and_reads_and_no_human_verb():
    assert set(AGENT_TOOLS) | set(READ_TOOLS) <= set(TOOLS)
    assert not set(TOOLS) & set(HUMAN_VERBS)
    listed = McpServer().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert names == set(TOOLS)
    for tool in listed["result"]["tools"]:
        # every description says what the tool does NOT do
        assert re.search(r"\b(not|never)\b", tool["description"]), tool["name"]


def test_a_human_verb_is_refused_as_an_unknown_tool():
    server = McpServer()
    cap_id = _ok(_call(server, "open_capture", {"image_path": str(DATA / "not_doc.jpg")}))[
        "capture_id"
    ]
    assert _ok(_call(server, "run_loop", {"capture_id": cap_id}))["state"] == "escalated"
    reply = _call(server, "approve", {"capture_id": cap_id})
    assert reply["error"]["code"] == -32602
    assert server.loop.captures[cap_id].state == "escalated"


def test_agent_tools_over_mcp_cannot_move_an_escalated_capture():
    server = McpServer()
    clean = _ok(_call(server, "open_capture", {"image_path": str(DATA / "clean_a.jpg")}))
    _ok(_call(server, "run_loop", clean))
    dup = _ok(_call(server, "open_capture", {"image_path": str(DATA / "dup_a.jpg")}))
    assert _ok(_call(server, "run_loop", dup))["state"] == "escalated"
    for name in ("decide_capture", "request_recapture", "inspect_capture"):
        reply = _call(server, name, dup)
        assert reply["result"]["isError"] is True
        assert "StateError" in reply["result"]["content"][0]["text"]
    assert server.loop.captures[dup["capture_id"]].state == "escalated"


def test_escalate_over_mcp_cannot_relabel_a_suspected_duplicate():
    server = McpServer()
    clean = _ok(_call(server, "open_capture", {"image_path": str(DATA / "clean_a.jpg")}))
    _ok(_call(server, "run_loop", clean))
    dup = _ok(_call(server, "open_capture", {"image_path": str(DATA / "dup_a.jpg")}))
    _ok(_call(server, "inspect_capture", dup))
    assert _ok(_call(server, "decide_capture", dup))["rule_id"] == "suspected_duplicate"
    reply = _call(server, "escalate", {**dup, "reason": "uncertain_band"})
    assert reply["result"]["isError"] is True
    assert server.loop.captures[dup["capture_id"]].state == "measured"
    _ok(_call(server, "escalate", dup))
    assert server.loop.captures[dup["capture_id"]].review_reason == "suspected_duplicate"


def test_a_batch_or_malformed_message_is_an_invalid_request_not_a_crash():
    server = McpServer()
    for message in ([{"jsonrpc": "2.0", "id": 1, "method": "ping"}], "ping", 7, None):
        reply = server.handle(message)
        assert reply is not None and reply["error"]["code"] == -32600, message
    reply = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": [1]})
    assert reply["error"]["code"] == -32602


def test_the_retake_chain_over_mcp_tool_by_tool():
    server = McpServer()
    first = _ok(_call(server, "open_capture", {"image_path": str(DATA / "glare_text.jpg")}))
    _ok(_call(server, "inspect_capture", first))
    verdict = _ok(_call(server, "decide_capture", first))
    assert (verdict["outcome"], verdict["rule_id"]) == ("retake", "glare_over_total")
    successor = _ok(_call(server, "request_recapture", first))
    _ok(
        _call(
            server,
            "attach_retake",
            {"capture_id": successor, "image_path": str(DATA / "crop_bottom.jpg")},
        )
    )
    second = _ok(_call(server, "run_loop", {"capture_id": successor}))
    assert second["verdict"]["rule_id"] == "bottom_edge_clipped"
    trace = _ok(_call(server, "get_trace", {"capture_id": successor}))
    assert [row["actor"] for row in trace] == ["agent"] * len(trace)


def test_stdio_transport_end_to_end():
    lines = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "open_capture",
                "arguments": {"image_path": str(DATA / "clean_b.jpg")},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "run_loop", "arguments": {"capture_id": "c_001"}},
        },
    ]
    result = subprocess.run(
        [sys.executable, str(ENTRY / "app" / "mcp_server.py")],
        input="".join(json.dumps(line) + "\n" for line in lines),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3]  # the notification got no reply
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert replies[0]["result"]["serverInfo"]["name"] == "second-look"
    assert replies[2]["result"]["structuredContent"]["result"]["state"] == "accepted"


def test_stdio_server_survives_a_batch_message():
    batch = [{"jsonrpc": "2.0", "id": 1, "method": "ping"}]
    after = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    result = subprocess.run(
        [sys.executable, str(ENTRY / "app" / "mcp_server.py")],
        input=json.dumps(batch) + "\n" + json.dumps(after) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert replies[0]["error"]["code"] == -32600
    assert replies[1] == {"jsonrpc": "2.0", "id": 2, "result": {}}
