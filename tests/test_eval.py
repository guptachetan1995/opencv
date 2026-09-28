"""The evaluation harness's two batch methodologies and its set R scorer."""

from __future__ import annotations

import json
import shutil

from eval.run_eval import load_manifest, run_real, run_shared_batch

from conftest import DATA


def test_shared_batch_is_scored_not_just_described():
    shared = run_shared_batch(load_manifest())
    assert shared.with_gt == 15
    assert shared.silent_accept_ids == []  # collisions escalate; none is accepted
    assert shared.matches == shared.with_gt - len(shared.collisions)
    glare = next(c for c in shared.collisions if c.sample_id == "glare_text")
    assert glare.nearest_distance <= 6


def test_set_r_is_absent_until_a_manifest_exists(tmp_path):
    assert run_real(tmp_path) is None


def test_set_r_scores_outcomes_against_hand_labels(tmp_path):
    for name in ("clean_b", "glare_text", "not_doc"):
        shutil.copy(DATA / f"{name}.jpg", tmp_path / f"{name}.jpg")
    manifest = {
        "licence": "test fixture",
        "consent": "n/a",
        "samples": [
            {"id": "r1", "file": "clean_b.jpg", "label": "accept", "defect": "clean"},
            {"id": "r2", "file": "glare_text.jpg", "label": "retake", "defect": "glare"},
            # A deliberately wrong label, so a disagreement is counted, not hidden.
            {"id": "r3", "file": "not_doc.jpg", "label": "accept", "defect": "clean"},
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    real = run_real(tmp_path)
    assert real is not None
    assert (real.total, real.agree, real.silent_accepts) == (3, 2, 0)
    assert real.count(label="accept", outcome="escalate") == 1
