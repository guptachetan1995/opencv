#!/usr/bin/env python3
"""Run SPEC § 7's demo script against the committed synthetic set and print the trace.

Three beats, each against a real image already in `data/synthetic/`:

1. `glare_text.jpg` retakes on `glare_over_total`; the retake (`crop_bottom.jpg` — the
   same underlying receipt, base "a", a different defect) fixes the glare and retakes
   again on a *different* rule, `bottom_edge_clipped` — the qualifying Agentic Vision
   beat, drawn as a line in `docs/agent-workflow.md`: OpenCV's output chose the next call.
2. `clean_a.jpg` and `clean_b.jpg` are accepted first, seeding the batch's accepted hashes.
3. `dup_a.jpg` escalates as a suspected duplicate of `clean_a.jpg`; a simulated reviewer
   clears the duplicate and approves it, the human-approval wait-then-resume this goal
   exists to demonstrate.

    python tools/run_demo.py

Exits 0 and prints only to stdout; no network, no AWS, no credential.
"""

from __future__ import annotations

import sys
from pathlib import Path

ENTRY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENTRY / "src"))

from secondlook.agent_loop import AgentLoop, invoke, process_capture  # noqa: E402

DATA = ENTRY / "data" / "synthetic"


def _print_trace(loop: AgentLoop, capture_id: str, title: str) -> None:
    print(f"\n-- trace: {title} --")
    print(f"{'seq':>3}  {'actor':<8} {'action':<18} inputs -> outputs (caused_by)")
    for row in loop.trace_chain(capture_id):
        print(
            f"{row['seq']:>3}  {row['actor']:<8} {row['action']:<18} "
            f"{row['inputs']} -> {row['outputs']}  (caused_by={row['caused_by']})"
        )


def main() -> int:
    # Beat 1: a bad capture, measured, then a different answer on the retake.
    retake_loop = AgentLoop()
    first_id = retake_loop.open_capture(DATA / "glare_text.jpg")
    first = process_capture(first_id, loop=retake_loop)
    print(
        f"glare_text.jpg -> {first.state} ({first.verdict.rule_id}): {first.verdict.reason_text}"
    )

    successor_id = next(
        e.outputs["successor_id"] for e in first.trace if e.action == "request_recapture"
    )
    retake_loop.attach_image(successor_id, DATA / "crop_bottom.jpg")
    second = process_capture(successor_id, loop=retake_loop)
    print(
        f"crop_bottom.jpg (retake) -> {second.state} ({second.verdict.rule_id}): "
        f"{second.verdict.reason_text}"
    )
    assert second.verdict.rule_id != first.verdict.rule_id, "the retake must fire a new rule"
    _print_trace(retake_loop, successor_id, "glare -> crop retake chain")

    # Beat 2 + 3: a clean batch, then a capture that is not the agent's to accept.
    batch_loop = AgentLoop()
    for sample in ("clean_a", "clean_b"):
        cap_id = batch_loop.open_capture(DATA / f"{sample}.jpg")
        cap = process_capture(cap_id, loop=batch_loop)
        print(f"{sample}.jpg -> {cap.state}")

    dup_id = batch_loop.open_capture(DATA / "dup_a.jpg")
    dup = process_capture(dup_id, loop=batch_loop)
    print(f"dup_a.jpg -> {dup.state} ({dup.verdict.rule_id}): {dup.verdict.reason_text}")
    assert dup.state == "escalated", "the agent must never auto-accept a suspected duplicate"

    invoke(
        "resolve_duplicate",
        {"capture_id": dup_id, "is_duplicate": False, "note": "two different lunches"},
        "reviewer",
        loop=batch_loop,
    )
    invoke(
        "approve",
        {"capture_id": dup_id, "note": "confirmed by reviewer"},
        "reviewer",
        loop=batch_loop,
    )
    resolved = batch_loop.captures[dup_id]
    print(f"reviewer resolves + approves -> {resolved.state}")
    _print_trace(batch_loop, dup_id, "escalation, resolved and approved")

    print("\nsecond look demo: all beats reached their SPEC § 7 verdict.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
