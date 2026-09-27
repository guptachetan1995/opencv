"""The agent loop: each promised behaviour of the chokepoint and the loop driver as one
test. Everything here reads a committed synthetic JPEG and calls `decide()`/`inspect_file()`
locally — no network, no credential, no model, deterministic policy only.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import fields

import pytest

from conftest import DATA, ENTRY, with_fields
from secondlook.agent_loop import (
    AGENT_TOOLS,
    HUMAN_VERBS,
    READ_TOOLS,
    AgentLoop,
    Capture,
    invoke,
    process_capture,
)
from secondlook.schema import TraceEntry


def _actions(capture) -> list[str]:
    return [entry.action for entry in capture.trace]


def _successor_of(capture, action: str = "request_recapture") -> str:
    entry = next(e for e in capture.trace if e.action == action)
    return entry.outputs["successor_id"]


# ---- "all tools and the approval action go through invoke(tool, args, actor)" ------------


def test_agent_tools_and_human_verbs_are_disjoint():
    """The human-only verbs are never registered on the agent — made checkable at the
    tool-registry level, not just documented."""
    assert not (set(AGENT_TOOLS) & set(HUMAN_VERBS))
    assert not (set(AGENT_TOOLS) & set(READ_TOOLS))
    assert set(AGENT_TOOLS) | set(HUMAN_VERBS) | set(READ_TOOLS) == {
        "inspect_capture",
        "decide_capture",
        "request_recapture",
        "compare_captures",
        "escalate",
        "approve",
        "reject",
        "resolve_duplicate",
        "get_capture",
        "get_trace",
    }


def test_invoke_refuses_the_wrong_actor():
    loop = AgentLoop()
    cap_id = loop.open_capture(DATA / "clean_a.jpg")

    with pytest.raises(PermissionError):
        invoke("inspect_capture", {"capture_id": cap_id}, "reviewer", loop=loop)
    assert loop.captures[cap_id].measurements is None  # refused, not silently run

    with pytest.raises(PermissionError):
        invoke("approve", {"capture_id": cap_id}, "agent", loop=loop)
    assert loop.captures[cap_id].state == "received"  # refused, not silently applied


def test_invoke_refuses_an_unknown_tool_or_actor():
    loop = AgentLoop()
    cap_id = loop.open_capture(DATA / "clean_a.jpg")
    with pytest.raises(ValueError):
        invoke("delete_everything", {"capture_id": cap_id}, "agent", loop=loop)
    with pytest.raises(ValueError):
        invoke("inspect_capture", {"capture_id": cap_id}, "owner", loop=loop)


# ---- "a test shows two inputs with different visual results taking different tool paths" -


def test_different_visual_results_take_different_tool_paths():
    # clean_b, not clean_a: glare_text is a glare-distorted version of clean_a's own
    # receipt (both base "a" in the manifest), so pairing it with clean_a in one batch
    # would trip the duplicate rule instead of showing the accept/retake split this test
    # is about. clean_b is a genuinely different receipt (base "b").
    loop = AgentLoop()
    clean_id = loop.open_capture(DATA / "clean_b.jpg")
    glare_id = loop.open_capture(DATA / "glare_text.jpg")

    clean = process_capture(clean_id, loop=loop)
    glare = process_capture(glare_id, loop=loop)

    assert clean.state == "accepted"
    assert glare.state == "awaiting_retake"
    assert _actions(clean) == ["inspect_capture", "decide_capture"]
    assert _actions(glare) == ["inspect_capture", "decide_capture", "request_recapture"]
    # The branch was chosen by decide_capture's own OpenCV-derived verdict, not by the test.
    assert clean.verdict.outcome == "accept"
    assert glare.verdict.outcome == "retake"
    assert glare.verdict.rule_id == "glare_over_total"


# ---- the headline beat: a different rule fires on a different metric ---------------------


def test_retake_chain_fires_a_different_rule_on_a_different_metric():
    """glare_text.jpg and crop_bottom.jpg are both base "a" in the committed manifest —
    the same receipt, two different defects — so this reproduces the demo's qualifying beat
    (glare fixed, crop found) from real committed images, not a hand-built fixture."""
    loop = AgentLoop()
    first_id = loop.open_capture(DATA / "glare_text.jpg")
    first = process_capture(first_id, loop=loop)
    assert first.state == "awaiting_retake"
    assert first.verdict.rule_id == "glare_over_total"

    successor_id = _successor_of(first)
    assert loop.captures[successor_id].state == "received"
    assert loop.captures[successor_id].parent_id == first_id
    assert loop.captures[successor_id].attempt == 2

    loop.attach_image(successor_id, DATA / "crop_bottom.jpg")
    second = process_capture(successor_id, loop=loop)

    assert second.state == "awaiting_retake"
    assert second.verdict.rule_id == "bottom_edge_clipped"
    assert second.verdict.rule_id != first.verdict.rule_id

    compare_entry = next(e for e in second.trace if e.action == "compare_captures")
    assert compare_entry.inputs["metric"] == "glare_over_text_frac"
    assert compare_entry.outputs["status"] == "fixed"

    decide_entries = [e for e in first.trace + second.trace if e.action == "decide_capture"]
    assert len(decide_entries) == 2
    assert decide_entries[0].outputs["rule_id"] != decide_entries[1].outputs["rule_id"]
    assert set(decide_entries[0].inputs) != set(decide_entries[1].inputs)


# ---- "an escalation waits for approval and resumes; the trace shows the evidence" --------


def test_escalation_waits_until_approved_then_resumes():
    loop = AgentLoop()
    clean_id = loop.open_capture(DATA / "clean_a.jpg")
    process_capture(clean_id, loop=loop)  # seeds accepted_hashes so dup_a can collide

    dup_id = loop.open_capture(DATA / "dup_a.jpg")
    dup = process_capture(dup_id, loop=loop)
    assert dup.state == "escalated"
    assert dup.review_reason == "suspected_duplicate"
    trace_len_at_escalation = len(dup.trace)

    # The wait: nothing in this module advances an escalated capture on its own.
    again = process_capture(dup_id, loop=loop)
    assert again.state == "escalated"
    assert len(again.trace) == trace_len_at_escalation

    decide_entry = next(e for e in dup.trace if e.action == "decide_capture")
    assert "nearest_distance" in decide_entry.inputs  # the evidence behind the escalation

    with pytest.raises(RuntimeError):
        invoke("approve", {"capture_id": dup_id}, "reviewer", loop=loop)  # not resolved yet

    invoke(
        "resolve_duplicate",
        {"capture_id": dup_id, "is_duplicate": False, "note": "two different lunches"},
        "reviewer",
        loop=loop,
    )
    assert loop.captures[dup_id].state == "escalated"  # still needs the second click

    invoke("approve", {"capture_id": dup_id, "note": "confirmed"}, "reviewer", loop=loop)

    # The resume: the human's invoke() call, and only it, moved the capture on.
    resumed = loop.captures[dup_id]
    assert resumed.state == "accepted"
    assert [e.actor for e in resumed.trace[-2:]] == ["reviewer", "reviewer"]


def test_reject_path_ends_the_capture():
    loop = AgentLoop()
    cap_id = loop.open_capture(DATA / "not_doc.jpg")
    cap = process_capture(cap_id, loop=loop)
    assert cap.state == "escalated"

    invoke("reject", {"capture_id": cap_id, "note": "not a receipt"}, "reviewer", loop=loop)
    assert loop.captures[cap_id].state == "rejected"

    # A rejected capture cannot be approved afterwards.
    with pytest.raises(RuntimeError):
        invoke("approve", {"capture_id": cap_id}, "reviewer", loop=loop)


def test_persistent_defect_escalates_after_two_retakes():
    """Exercises decide_capture's own attempt/parent-reason wiring through invoke(), not
    just policy.py's pure function (test_policy.py already covers that in isolation)."""
    loop = AgentLoop()
    glare_fixture = with_fields(glare_over_text_frac=0.4, glare_boxes=[[300, 900, 250, 60]])

    parent_id = loop.open_capture()
    loop.captures[parent_id].attempt = 2
    loop.captures[parent_id].measurements = glare_fixture
    invoke("decide_capture", {"capture_id": parent_id}, "agent", loop=loop)
    assert loop.captures[parent_id].verdict.rule_id == "glare_over_total"

    child_id = loop.open_capture(parent_id=parent_id)
    assert loop.captures[child_id].attempt == 3
    loop.captures[child_id].measurements = glare_fixture
    invoke("decide_capture", {"capture_id": child_id}, "agent", loop=loop)

    child_verdict = loop.captures[child_id].verdict
    assert (child_verdict.outcome, child_verdict.rule_id) == ("escalate", "persistent_defect")
    assert loop.captures[child_id].state == "measured"  # decide never escalates on its own


# ---- "all tools and the approval action go through invoke() ... asserts identical state" -


def test_tool_path_and_approval_path_reach_identical_state_shape():
    """One capture reaches "accepted" through agent tool calls alone (auto-accept);
    another reaches it only via escalate -> resolve_duplicate -> approve. Both routes are
    nothing but invoke() calls into the same AgentLoop — proving the human path and the
    tool path mutate one store through one chokepoint, not two."""
    loop = AgentLoop()

    tool_path_id = loop.open_capture(DATA / "clean_a.jpg")
    process_capture(tool_path_id, loop=loop)

    accepted_first_id = loop.open_capture(DATA / "clean_b.jpg")
    process_capture(accepted_first_id, loop=loop)  # a second accepted capture in the batch

    approval_path_id = loop.open_capture(DATA / "dup_a.jpg")
    process_capture(approval_path_id, loop=loop)
    invoke(
        "resolve_duplicate",
        {"capture_id": approval_path_id, "is_duplicate": False},
        "reviewer",
        loop=loop,
    )
    invoke("approve", {"capture_id": approval_path_id, "note": "ok"}, "reviewer", loop=loop)

    tool_path = loop.captures[tool_path_id]
    approval_path = loop.captures[approval_path_id]

    assert tool_path.state == approval_path.state == "accepted"
    assert {f.name for f in fields(tool_path)} == {f.name for f in fields(approval_path)}
    for cap in (tool_path, approval_path):
        assert isinstance(cap, Capture)
        assert cap.measurements is not None
        assert cap.verdict is not None
        assert cap.trace and all(isinstance(e, TraceEntry) for e in cap.trace)
        assert loop.accepted_hashes[cap.capture_id] == cap.measurements.phash
    # Only the paths taken to get there differ — the tool path never saw a reviewer, the
    # approval path never auto-accepted.
    assert "reviewer" not in {e.actor for e in tool_path.trace}
    assert "reviewer" in {e.actor for e in approval_path.trace}
    assert tool_path.verdict.decided_by == approval_path.verdict.decided_by == "policy"


# ---- open_capture is safe under concurrent requests ----------------------------------------


def test_open_capture_never_mints_a_duplicate_id_under_concurrent_calls():
    """app/server.py's ThreadingHTTPServer serves one shared AgentLoop from multiple OS
    threads; the counter increment is a read-modify-write, so without a lock two
    concurrent requests could compute the same next id and overwrite each other's slot."""
    import threading

    loop = AgentLoop()
    ids: list[str] = []
    ids_lock = threading.Lock()

    def open_one():
        capture_id = loop.open_capture(DATA / "clean_a.jpg")
        with ids_lock:
            ids.append(capture_id)

    threads = [threading.Thread(target=open_one) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(ids) == 50
    assert len(set(ids)) == 50, "duplicate capture_id minted under concurrent open_capture"
    assert len(loop.captures) == 50


# ---- the trace is evidence, not just a log -----------------------------------------------


def test_trace_chain_reconstructs_the_spec_demo_shape():
    loop = AgentLoop()
    first_id = loop.open_capture(DATA / "glare_text.jpg")
    process_capture(first_id, loop=loop)
    successor_id = _successor_of(loop.captures[first_id])
    loop.attach_image(successor_id, DATA / "crop_bottom.jpg")
    process_capture(successor_id, loop=loop)

    chain = loop.trace_chain(successor_id)
    assert [row["seq"] for row in chain] == list(range(1, len(chain) + 1))
    assert chain[0]["caused_by"] is None
    for row in chain[1:]:
        assert row["caused_by"] is not None
        assert row["caused_by"] < row["seq"]
    # The successor's first entry (compare_captures) is caused by the parent's
    # request_recapture entry — the cross-capture link the demo trace prints.
    request_seq = next(r["seq"] for r in chain if r["action"] == "request_recapture")
    compare_seq = next(r["seq"] for r in chain if r["action"] == "compare_captures")
    assert chain[compare_seq - 1]["caused_by"] == request_seq


# ---- the demo script runs end to end -----------------------------------------------------


def test_demo_script_runs_end_to_end():
    result = subprocess.run(
        [sys.executable, str(ENTRY / "tools" / "run_demo.py")],
        cwd=ENTRY,
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    for beat in ("glare_over_total", "bottom_edge_clipped", "suspected_duplicate", "accepted"):
        assert beat in out, out
