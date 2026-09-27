"""Policy: table-driven, one fixture per rule; first-match-wins is asserted
explicitly; ``firings`` records every rule evaluated, not only the one that matched."""

from __future__ import annotations

import pytest

from conftest import clean_measurements, with_fields
from secondlook import Verdict, decide

CASCADE = [
    "not_a_document",
    "two_documents",
    "suspected_duplicate",
    "persistent_defect",
    "bottom_edge_clipped",
    "glare_over_total",
    "out_of_focus",
    "underexposed",
    "overexposed",
    "uncertain",
    "accept",
]

# One fixture per rule: the single change to the clean record that makes that rule fire.
FIXTURES = {
    "not_a_document": dict(quad_found=False, quad=None),
    "two_documents": dict(second_quad_area_fraction=0.12),
    "suspected_duplicate": dict(nearest_distance=3, duplicate_of="c_other"),
    "bottom_edge_clipped": dict(edge_touch_sides=["bottom"], bottom_band_has_text=True),
    "glare_over_total": dict(glare_over_text_frac=0.4, glare_boxes=[[300, 900, 250, 60]]),
    "out_of_focus": dict(focus_min_tile=0.4, blur_tiles=[[0, 1400, 133, 206]]),
    "underexposed": dict(clipped_low_frac=0.8),
    "overexposed": dict(clipped_high_frac=0.9),
    "uncertain": dict(glare_over_text_frac=0.13),
    "accept": {},
}


def test_cascade_order_is_the_spec_order(policy):
    assert policy.rule_ids == CASCADE


def test_clean_record_is_accepted(policy):
    verdict = decide(clean_measurements(), policy)
    assert (verdict.outcome, verdict.rule_id, verdict.reason_code) == ("accept", "accept", "clean")
    assert verdict.decided_by == "policy"
    assert verdict.hint_box is None


@pytest.mark.parametrize("rule_id", list(FIXTURES))
def test_each_rule_fires_on_its_own_fixture(policy, rule_id):
    verdict = decide(with_fields(**FIXTURES[rule_id]), policy)
    assert verdict.rule_id == rule_id
    expected = next(r for r in policy.rules if r["id"] == rule_id)
    assert verdict.outcome == expected["outcome"]
    assert verdict.reason_code == expected["reason_code"]
    assert verdict.reason_text == expected["reason_text"]


@pytest.mark.parametrize("rule_id", [r for r in FIXTURES if r not in ("accept", "uncertain")])
def test_each_fixture_fires_no_other_rule(policy, rule_id):
    """A fixture built for one rule must not trip any *other* rule earlier in the cascade."""
    verdict = decide(with_fields(**FIXTURES[rule_id]), policy)
    fired = {f.rule_id for f in verdict.firings if f.matched}
    assert fired == {rule_id}


def test_first_match_wins_duplicate_beats_glare(policy):
    both = with_fields(**FIXTURES["suspected_duplicate"], **FIXTURES["glare_over_total"])
    verdict = decide(both, policy)
    assert verdict.rule_id == "suspected_duplicate"
    assert verdict.outcome == "escalate"
    assert "glare_over_total" not in {f.rule_id for f in verdict.firings}


def test_firings_record_every_rule_evaluated_up_to_the_match(policy):
    verdict = decide(with_fields(**FIXTURES["underexposed"]), policy)
    evaluated = []
    for f in verdict.firings:
        if f.rule_id not in evaluated:
            evaluated.append(f.rule_id)
    assert evaluated == CASCADE[: CASCADE.index("underexposed") + 1]
    for f in verdict.firings:
        assert f.metric and f.comparison
        assert isinstance(f.matched, bool)


def test_persistent_defect_after_two_retakes(policy):
    glare = with_fields(**FIXTURES["glare_over_total"])
    assert (
        decide(glare, policy, attempt=2, parent_reason_code="glare_over_total").rule_id
        == "glare_over_total"
    )
    third = decide(glare, policy, attempt=3, parent_reason_code="glare_over_total")
    assert (third.outcome, third.rule_id) == ("escalate", "persistent_defect")
    # A third attempt with a *different* defect is still a retake, not an escalation.
    assert (
        decide(glare, policy, attempt=3, parent_reason_code="out_of_focus").rule_id
        == "glare_over_total"
    )
    # Recorded as two clauses: the attempt count and the would-be reason code.
    rows = [f for f in third.firings if f.rule_id == "persistent_defect"]
    assert [(r.metric, r.matched) for r in rows] == [("attempt", True), ("reason_code", True)]


def test_decoded_code_cancels_the_focus_retake(policy):
    soft = with_fields(
        focus_min_tile=0.4, blur_tiles=[[0, 0, 133, 206]], code_kind="qr", code_decoded=True
    )
    verdict = decide(soft, policy)
    assert verdict.rule_id == "accept"
    focus_rows = [f for f in verdict.firings if f.rule_id == "out_of_focus"]
    # Neither row is "matched": the rule did not fire. The values still tell the story.
    assert [(r.metric, r.value, r.matched) for r in focus_rows] == [
        ("focus_min_tile", 0.4, False),
        ("code_decoded", True, False),
    ]


def test_uncertain_band_escalates_and_names_the_metric(policy):
    verdict = decide(with_fields(focus_min_tile=2.5), policy)
    assert (verdict.outcome, verdict.rule_id, verdict.reason_code) == (
        "escalate",
        "uncertain",
        "uncertain_band",
    )
    within = [f for f in verdict.firings if f.rule_id == "uncertain" and f.matched]
    assert [(f.metric, f.comparison, f.threshold) for f in within] == [
        ("focus_min_tile", "within", [1.25, 2.75])
    ]


def test_suspected_duplicate_can_never_be_accepted(policy):
    for distance in range(0, 7):
        verdict = decide(with_fields(nearest_distance=distance), policy)
        assert verdict.outcome == "escalate"
        assert verdict.rule_id == "suspected_duplicate"


def test_hint_boxes_point_at_the_failure(policy):
    glare = decide(with_fields(**FIXTURES["glare_over_total"]), policy)
    assert glare.hint_box == [300, 900, 250, 60]
    focus = decide(with_fields(**FIXTURES["out_of_focus"]), policy)
    assert focus.hint_box == [0, 1400, 133, 206]
    clipped = decide(with_fields(**FIXTURES["bottom_edge_clipped"]), policy)
    assert clipped.hint_box == [0, 1452, 800, 198]
    dark = decide(with_fields(**FIXTURES["underexposed"]), policy)
    assert dark.hint_box == [0, 0, 800, 1650]


def test_verdict_round_trips_through_json_dict(policy):
    verdict = decide(with_fields(**FIXTURES["glare_over_total"]), policy)
    again = Verdict.from_dict(verdict.to_dict())
    assert again == verdict


def test_decide_is_pure(policy):
    record = with_fields(**FIXTURES["out_of_focus"])
    first = decide(record, policy)
    second = decide(record, policy)
    assert first == second
    assert record == with_fields(**FIXTURES["out_of_focus"])
