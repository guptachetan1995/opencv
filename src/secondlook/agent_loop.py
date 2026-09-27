"""The agent loop: perception -> decision -> action.

Wraps ``inspect()`` and ``decide()`` as the agent tools and human verbs listed in the
README, dispatched through a single chokepoint, ``invoke(tool, args, actor)``. Every tool
call and every human verb mutates a ``Capture`` only by passing through ``invoke``;
``process_capture`` (the loop driver) never touches a ``Capture`` directly, and neither
does anything else in this module.

This is an in-memory precursor to a planned ``apply.py`` / ``store.py`` pair (S3-backed
persistence, not built). When that layer lands, it folds this module's ``invoke`` into
``apply.py`` rather than keeping two chokepoints.

**Not implemented here:** ``override`` and ``discard`` (the human-only verbs that would
overturn a verdict or delete a capture) and ``close_batch``. The demo needs only
``approve``, ``reject`` and ``resolve_duplicate`` to show a real
wait-for-approval-then-resume.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from secondlook.perception import inspect_file
from secondlook.policy import Policy, decide, load_policy
from secondlook.schema import Measurements, TraceEntry, Verdict

State = str  # "received" | "measured" | "awaiting_retake" | "escalated" | "accepted" | "rejected"

# The agent/human split, enforced at the chokepoint rather than merely documented: the
# human-only verbs are never registered as agent tools, and tests assert it.
AGENT_TOOLS = (
    "inspect_capture",
    "decide_capture",
    "request_recapture",
    "compare_captures",
    "escalate",
)
HUMAN_VERBS = ("approve", "reject", "resolve_duplicate")
READ_TOOLS = ("get_capture", "get_trace")

# The one metric each retake-triggering rule reads (`request_recapture` names the one
# metric that failed; `compare_captures` reports only that metric).
_FAILING_METRIC = {
    "bottom_edge_clipped": "edge_touch_sides",
    "glare_over_total": "glare_over_text_frac",
    "out_of_focus": "focus_min_tile",
    "underexposed": "clipped_low_frac",
    "overexposed": "clipped_high_frac",
}
# Whether a *lower* or a *higher* value is the fixed direction, for the scalar metrics above.
_BETTER_DIRECTION = {
    "glare_over_text_frac": "lower",
    "focus_min_tile": "higher",
    "clipped_low_frac": "lower",
    "clipped_high_frac": "lower",
}


@dataclass
class Capture:
    """One capture's live state. Mutated only by the handlers ``invoke`` dispatches to."""

    capture_id: str
    image_path: Path | None
    batch_id: str = "b_demo"
    parent_id: str | None = None
    attempt: int = 1
    state: State = "received"
    measurements: Measurements | None = None
    verdict: Verdict | None = None
    review_reason: str | None = None
    duplicate_resolved: bool = False
    # (parent_capture_id, parent's local trace seq for the request_recapture that opened
    # this slot) — lets `AgentLoop.trace_chain` draw the cross-capture causal arrow the
    # demo trace shows without merging two captures' trace lists into one.
    opened_by: tuple[str, int] | None = None
    trace: list[TraceEntry] = field(default_factory=list)

    def record(
        self, actor: str, action: str, inputs: dict[str, Any], outputs: dict[str, Any]
    ) -> TraceEntry:
        caused_by = self.trace[-1].seq if self.trace else None
        entry = TraceEntry(
            seq=len(self.trace) + 1,
            at=datetime.now(UTC).isoformat(),
            actor=actor,
            action=action,
            inputs=inputs,
            outputs=outputs,
            caused_by=caused_by,
        )
        self.trace.append(entry)
        return entry


@dataclass
class AgentLoop:
    """The in-memory store for one open batch. Nothing outside this module's handlers
    reads or writes ``captures`` or ``accepted_hashes`` directly."""

    policy: Policy = field(default_factory=load_policy)
    captures: dict[str, Capture] = field(default_factory=dict)
    # Only ACCEPTED captures count as "the batch" for duplicate detection: measurement 8's
    # Hamming distance is taken against the already-accepted set.
    accepted_hashes: dict[str, str] = field(default_factory=dict)
    _counter: int = 0
    # app/server.py's ThreadingHTTPServer serves one shared AgentLoop from multiple OS
    # threads; "+= 1" is a read-modify-write, not atomic, so two concurrent requests could
    # otherwise mint the same capture_id and overwrite each other's slot.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def open_capture(
        self, image_path: str | Path | None = None, *, parent_id: str | None = None
    ) -> str:
        """A photo landing in a slot — plumbing, not a tool. Nobody decides anything by a
        capture merely existing, so this is never gated by ``invoke``."""
        with self._lock:
            self._counter += 1
            capture_id = f"c_{self._counter:03d}"
            attempt = self.captures[parent_id].attempt + 1 if parent_id else 1
            self.captures[capture_id] = Capture(
                capture_id=capture_id,
                image_path=Path(image_path) if image_path else None,
                parent_id=parent_id,
                attempt=attempt,
            )
        return capture_id

    def attach_image(self, capture_id: str, image_path: str | Path) -> None:
        """The retake photo arriving for a slot ``request_recapture`` already opened.
        Also plumbing: no measurement, decision or state change happens here."""
        self.captures[capture_id].image_path = Path(image_path)

    def trace_chain(self, capture_id: str) -> list[dict[str, Any]]:
        """Flatten this capture's trace and every ancestor's into one globally-numbered
        sequence (the table ``tools/run_demo.py`` prints), resolving each capture's
        ``opened_by`` into a cross-capture ``caused_by``."""
        chain: list[str] = []
        cursor: str | None = capture_id
        while cursor is not None:
            chain.append(cursor)
            cursor = self.captures[cursor].parent_id
        chain.reverse()

        flat: list[dict[str, Any]] = []
        global_seq: dict[tuple[str, int], int] = {}
        for cap_id in chain:
            cap = self.captures[cap_id]
            for entry in cap.trace:
                seq = len(flat) + 1
                global_seq[(cap_id, entry.seq)] = seq
                caused_by = global_seq.get((cap_id, entry.caused_by)) if entry.caused_by else None
                if caused_by is None and entry.caused_by is None and cap.opened_by is not None:
                    caused_by = global_seq.get(cap.opened_by)
                flat.append(
                    {
                        "seq": seq,
                        "at": entry.at,
                        "actor": entry.actor,
                        "action": entry.action,
                        "inputs": entry.inputs,
                        "outputs": entry.outputs,
                        "caused_by": caused_by,
                    }
                )
        return flat


_default_loop: AgentLoop | None = None


def default_loop() -> AgentLoop:
    """The module-level batch `invoke` and `process_capture` fall back to when no
    explicit ``loop`` is given. Tests and the demo script pass their own ``loop`` for
    isolation instead of relying on this."""
    global _default_loop
    if _default_loop is None:
        _default_loop = AgentLoop()
    return _default_loop


def invoke(
    tool: str, args: dict[str, Any] | None, actor: str, *, loop: AgentLoop | None = None
) -> Any:
    """The single chokepoint: every agent tool and every human verb is a call into this
    function. Every mutation in this module happens here or not at all —
    ``process_capture`` and the demo script only ever call this function."""
    if actor not in ("agent", "reviewer"):
        raise ValueError(f"unknown actor: {actor!r}")
    handler = _HANDLERS.get(tool)
    if handler is None:
        raise ValueError(f"unknown tool: {tool!r}")
    if tool in HUMAN_VERBS and actor != "reviewer":
        raise PermissionError(f"{tool!r} is human-only; actor was {actor!r}")
    if tool in AGENT_TOOLS and actor != "agent":
        raise PermissionError(f"{tool!r} is an agent tool; actor was {actor!r}")
    return handler(loop or default_loop(), **(args or {}))


# ---- agent tools -----------------------------------------------------------------------


def _inspect_capture(loop: AgentLoop, capture_id: str) -> Measurements:
    cap = loop.captures[capture_id]
    if cap.image_path is None:
        raise RuntimeError(f"{capture_id} has no image yet — attach_image before inspecting")
    measurements = inspect_file(
        cap.image_path, known_hashes=dict(loop.accepted_hashes), policy=loop.policy
    )
    cap.measurements = measurements
    if cap.state == "received":
        cap.state = "measured"
    cap.record(
        "agent",
        "inspect_capture",
        {"image_shape": measurements.image_shape},
        {"phash": measurements.phash, "nearest_distance": measurements.nearest_distance},
    )
    return measurements


def _decide_capture(loop: AgentLoop, capture_id: str) -> Verdict:
    cap = loop.captures[capture_id]
    if cap.measurements is None:
        raise RuntimeError(f"{capture_id} has no measurement record; call inspect_capture first")
    parent_reason = None
    if cap.parent_id is not None:
        parent_verdict = loop.captures[cap.parent_id].verdict
        parent_reason = parent_verdict.reason_code if parent_verdict else None
    verdict = decide(
        cap.measurements, loop.policy, attempt=cap.attempt, parent_reason_code=parent_reason
    )
    cap.verdict = verdict
    matched = {f.metric: f.value for f in verdict.firings if f.matched}
    outputs = {
        "outcome": verdict.outcome,
        "rule_id": verdict.rule_id,
        "reason_code": verdict.reason_code,
    }
    cap.record("agent", "decide_capture", matched or {"rule_id": verdict.rule_id}, outputs)
    if verdict.outcome == "accept":
        # Auto-accepting a capture that is comfortably inside every band is not a separate
        # tool call — it is what deciding "accept" does.
        cap.state = "accepted"
        _mark_accepted(loop, cap)
    else:
        cap.state = "measured"
    return verdict


def _request_recapture(
    loop: AgentLoop, capture_id: str, failing_metric: str, hint_box: list[int] | None
) -> str:
    cap = loop.captures[capture_id]
    successor_id = loop.open_capture(parent_id=capture_id)
    entry = cap.record(
        "agent",
        "request_recapture",
        {"failing_metric": failing_metric},
        {"hint_box": hint_box, "successor_id": successor_id},
    )
    cap.state = "awaiting_retake"
    loop.captures[successor_id].opened_by = (capture_id, entry.seq)
    return successor_id


def _compare_captures(loop: AgentLoop, previous_id: str, new_id: str) -> str:
    previous = loop.captures[previous_id]
    new = loop.captures[new_id]
    if previous.verdict is None:
        raise RuntimeError(f"{previous_id} has no verdict; nothing to compare against")
    if new.image_path is None:
        raise RuntimeError(f"{new_id} has no image yet — attach_image before comparing")
    metric = _FAILING_METRIC.get(previous.verdict.rule_id, previous.verdict.rule_id)
    remeasured = inspect_file(
        new.image_path, known_hashes=dict(loop.accepted_hashes), policy=loop.policy
    )
    before = getattr(previous.measurements, metric, None)
    after = getattr(remeasured, metric, None)
    status = _compare_status(metric, before, after)
    new.record(
        "agent",
        "compare_captures",
        {"metric": metric, "before": before},
        {"after": after, "status": status},
    )
    return status


def _escalate(loop: AgentLoop, capture_id: str, reason: str) -> None:
    cap = loop.captures[capture_id]
    cap.record("agent", "escalate", {"reason": reason}, {"review_item": "opened"})
    cap.state = "escalated"
    cap.review_reason = reason


# ---- human-only verbs (never in AGENT_TOOLS; `invoke` refuses actor="agent" for these) --


def _approve(loop: AgentLoop, capture_id: str, note: str | None = None) -> None:
    cap = _require_escalated(loop, capture_id)
    if cap.review_reason == "suspected_duplicate" and not cap.duplicate_resolved:
        raise RuntimeError(
            f"{capture_id} is a suspected duplicate; resolve_duplicate before approving"
        )
    cap.record("reviewer", "approve", {"note": note}, {"state": "accepted"})
    cap.state = "accepted"
    _mark_accepted(loop, cap)


def _reject(loop: AgentLoop, capture_id: str, note: str | None = None) -> None:
    cap = _require_escalated(loop, capture_id)
    cap.record("reviewer", "reject", {"note": note}, {"state": "rejected"})
    cap.state = "rejected"


def _resolve_duplicate(
    loop: AgentLoop, capture_id: str, is_duplicate: bool, note: str | None = None
) -> None:
    cap = _require_escalated(loop, capture_id)
    if cap.review_reason != "suspected_duplicate":
        raise RuntimeError(f"{capture_id} was not escalated as a suspected duplicate")
    cap.record(
        "reviewer",
        "resolve_duplicate",
        {"is_duplicate": is_duplicate, "note": note},
        {"duplicate": "confirmed" if is_duplicate else "cleared"},
    )
    if is_duplicate:
        cap.state = "rejected"
    else:
        cap.duplicate_resolved = True
    # A cleared duplicate stays "escalated" until the separate `approve` call above runs:
    # the reviewer's decision is two steps, "not a duplicate" and then "approve".


def _require_escalated(loop: AgentLoop, capture_id: str) -> Capture:
    cap = loop.captures[capture_id]
    if cap.state != "escalated":
        raise RuntimeError(f"{capture_id} is not awaiting review (state={cap.state!r})")
    return cap


# ---- reads: no actor restriction, no trace entry ----------------------------------------


def _get_capture(loop: AgentLoop, capture_id: str) -> Capture:
    return loop.captures[capture_id]


def _get_trace(loop: AgentLoop, capture_id: str) -> list[dict[str, Any]]:
    return loop.trace_chain(capture_id)


_HANDLERS: dict[str, Callable[..., Any]] = {
    "inspect_capture": _inspect_capture,
    "decide_capture": _decide_capture,
    "request_recapture": _request_recapture,
    "compare_captures": _compare_captures,
    "escalate": _escalate,
    "approve": _approve,
    "reject": _reject,
    "resolve_duplicate": _resolve_duplicate,
    "get_capture": _get_capture,
    "get_trace": _get_trace,
}


def _mark_accepted(loop: AgentLoop, cap: Capture) -> None:
    if cap.measurements is not None:
        loop.accepted_hashes[cap.capture_id] = cap.measurements.phash


def _compare_status(metric: str, before: Any, after: Any) -> str:
    if isinstance(before, list) or isinstance(after, list):
        before_set, after_set = set(before or []), set(after or [])
        if not after_set:
            return "fixed"
        if before_set == after_set:
            return "unchanged"
        return "fixed" if len(after_set) < len(before_set) else "worse"
    direction = _BETTER_DIRECTION.get(metric)
    if direction is None or before is None or after is None:
        return "unchanged"
    if direction == "lower":
        if after < before * 0.5:
            return "fixed"
        return "worse" if after > before else "unchanged"
    if after > before * 1.5:
        return "fixed"
    return "worse" if after < before else "unchanged"


# ---- the loop driver ---------------------------------------------------------------------


def process_capture(capture_id: str, *, loop: AgentLoop | None = None) -> Capture:
    """Perception -> decision -> action for one capture: this is where OpenCV's output
    chooses the *next* `invoke()` call, not a person or a test script. Only runs the
    automated steps while the capture is freshly `"received"`; called again on a capture
    that is `"awaiting_retake"`, `"escalated"`, `"accepted"` or `"rejected"` it is a no-op
    — that is the literal mechanism behind "an escalation waits for approval": once
    `escalate` has run, nothing in this module advances the capture again until a human's
    `invoke()` call does.
    """
    loop = loop or default_loop()
    cap = loop.captures[capture_id]
    if cap.state != "received":
        return cap
    if cap.image_path is None:
        raise RuntimeError(f"{capture_id} has no image yet — attach_image before processing")

    if cap.parent_id is not None:
        invoke(
            "compare_captures",
            {"previous_id": cap.parent_id, "new_id": capture_id},
            "agent",
            loop=loop,
        )
    invoke("inspect_capture", {"capture_id": capture_id}, "agent", loop=loop)
    verdict = invoke("decide_capture", {"capture_id": capture_id}, "agent", loop=loop)

    if verdict.outcome == "retake":
        invoke(
            "request_recapture",
            {
                "capture_id": capture_id,
                "failing_metric": _FAILING_METRIC.get(verdict.rule_id, verdict.rule_id),
                "hint_box": verdict.hint_box,
            },
            "agent",
            loop=loop,
        )
    elif verdict.outcome == "escalate":
        invoke(
            "escalate",
            {"capture_id": capture_id, "reason": verdict.reason_code},
            "agent",
            loop=loop,
        )
    return loop.captures[capture_id]
