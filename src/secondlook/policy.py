"""The decision layer: ``decide(measurements, policy) -> Verdict`` (SPEC § 8).

A pure function over the ordered rule cascade in ``policy.toml``. First match wins; every
clause evaluated is recorded as a ``RuleFiring`` so the trace explains the verdict without
the code. Nothing here touches OpenCV, the store, or the network.
"""

from __future__ import annotations

import operator
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from secondlook.schema import Box, Measurements, RuleFiring, Verdict

DEFAULT_POLICY_PATH = Path(__file__).with_name("policy.toml")

_OPS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "contains": lambda a, b: b in a,
}


@dataclass(frozen=True)
class PerceptionConfig:
    canonical_page_width: int
    canny_low: int
    canny_high: int
    page_area_floor: float
    focus_grid: tuple[int, int]
    focus_tile_ink_min: float
    blur_tile_threshold: float
    exposure_low_level: int
    exposure_high_level: int
    glare_saturation_max: int
    glare_value_min: int
    glare_min_area_fraction: float
    glare_max_area_fraction: float
    text_contrast_min: float
    text_darkness_min: int
    text_min_height_px: int
    text_max_height_px: int
    text_boxes_cap: int
    bottom_band_fraction: float
    edge_touch_margin_fraction: float
    duplicate_hamming_threshold: int


@dataclass(frozen=True)
class Policy:
    path: Path
    perception: PerceptionConfig
    rules: list[dict[str, Any]]

    @property
    def rule_ids(self) -> list[str]:
        return [r["id"] for r in self.rules]


def load_policy(path: Path | str | None = None) -> Policy:
    path = Path(path) if path else DEFAULT_POLICY_PATH
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    perception = dict(raw["perception"])
    perception["focus_grid"] = tuple(perception["focus_grid"])
    return Policy(path=path, perception=PerceptionConfig(**perception), rules=list(raw["rule"]))


def decide(
    measurements: Measurements,
    policy: Policy,
    *,
    attempt: int = 1,
    parent_reason_code: str | None = None,
) -> Verdict:
    """Run the cascade. ``attempt`` and ``parent_reason_code`` come from the capture record."""
    values = measurements.to_dict()
    values["attempt"] = attempt
    firings: list[RuleFiring] = []
    rule = _first_match(policy.rules, values, parent_reason_code, firings)
    return Verdict(
        outcome=rule["outcome"],
        rule_id=rule["id"],
        reason_code=rule["reason_code"],
        reason_text=rule["reason_text"],
        hint_box=_hint_box(rule["hint"], measurements, policy.perception),
        firings=firings,
        decided_by="policy",
    )


def _first_match(
    rules: list[dict[str, Any]],
    values: dict[str, Any],
    parent_reason_code: str | None,
    firings: list[RuleFiring] | None,
) -> dict[str, Any]:
    for index, rule in enumerate(rules):
        special = rule.get("special")
        if special == "persistent_defect":
            matched = _persistent_defect(
                rule, rules[index + 1 :], values, parent_reason_code, firings
            )
        elif special == "uncertain":
            matched = _uncertain(rule, rules, values, firings)
        else:
            matched = _plain(rule, values, firings)
        if matched:
            return rule
    raise RuntimeError("policy cascade has no unconditional final rule")


def _plain(rule: dict[str, Any], values: dict[str, Any], firings: list[RuleFiring] | None) -> bool:
    """Evaluate a rule's clauses. A row's ``matched`` says whether that clause contributed to
    the rule matching (clause true AND rule true), so a trace never shows a "matched" row
    under a rule that did not fire."""
    rows = []
    for clause in rule["clauses"]:
        value = values[clause["metric"]]
        rows.append((bool(_OPS[clause["op"]](value, clause["value"])), clause, value))
    if not rows:
        return True
    results = [ok for ok, _, _ in rows]
    matched = all(results) if rule["combine"] == "all" else any(results)
    for ok, clause, value in rows:
        _record(
            firings,
            rule["id"],
            ok and matched,
            clause["metric"],
            value,
            clause["value"],
            clause["op"],
        )
    return matched


def _persistent_defect(
    rule: dict[str, Any],
    rest: list[dict[str, Any]],
    values: dict[str, Any],
    parent_reason_code: str | None,
    firings: list[RuleFiring] | None,
) -> bool:
    attempt_ok = _plain(rule, values, None)
    would_be = _first_match(rest, values, parent_reason_code, None)
    same = parent_reason_code is not None and would_be["reason_code"] == parent_reason_code
    matched = attempt_ok and same
    clause = rule["clauses"][0]
    _record(
        firings,
        rule["id"],
        matched,
        clause["metric"],
        values[clause["metric"]],
        clause["value"],
        clause["op"],
    )
    _record(
        firings,
        rule["id"],
        matched,
        "reason_code",
        would_be["reason_code"],
        parent_reason_code,
        "==",
    )
    return matched


def _uncertain(
    rule: dict[str, Any],
    rules: list[dict[str, Any]],
    values: dict[str, Any],
    firings: list[RuleFiring] | None,
) -> bool:
    matched = False
    for other in rules:
        for clause in other["clauses"]:
            margin = clause.get("margin")
            if margin is None:
                continue
            value = values[clause["metric"]]
            band = [clause["value"] - margin, clause["value"] + margin]
            within = band[0] <= value <= band[1]
            matched = matched or within
            _record(firings, rule["id"], within, clause["metric"], value, band, "within")
    return matched


def _record(
    firings: list[RuleFiring] | None,
    rule_id: str,
    matched: bool,
    metric: str,
    value: Any,
    threshold: Any,
    comparison: str,
) -> None:
    if firings is not None:
        firings.append(RuleFiring(rule_id, matched, metric, value, threshold, comparison))


def _hint_box(hint: str, m: Measurements, cfg: PerceptionConfig) -> Box | None:
    page_h, page_w = m.page_shape
    if hint == "glare_boxes" and m.glare_boxes:
        return max(m.glare_boxes, key=lambda b: b[2] * b[3])
    if hint == "blur_tiles" and m.blur_tiles:
        return m.blur_tiles[0]  # perception sorts blur tiles worst-first
    if hint == "bottom_band":
        top = int(round(page_h * (1.0 - cfg.bottom_band_fraction)))
        return [0, top, page_w, page_h - top]
    if hint == "page":
        return [0, 0, page_w, page_h]
    return None
