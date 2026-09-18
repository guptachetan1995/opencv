"""Golden outputs: the committed synthetic set, its manifest, and the verdict the policy
reaches on every sample with an expected verdict. Also the checked-in size budget and
that the generator reproduces the set from its seed."""

from __future__ import annotations

import json
import subprocess
import sys

import cv2
import numpy as np
import pytest

from conftest import DATA, ENTRY
from secondlook import decide, inspect_file

SIZE_BUDGET_BYTES = 20 * 1024 * 1024


def test_manifest_and_files_agree(manifest):
    ids = [s["id"] for s in manifest["samples"]]
    assert len(ids) == len(set(ids))
    for s in manifest["samples"]:
        assert (DATA / s["file"]).is_file(), s["file"]
    on_disk = {p.name for p in DATA.glob("*.jpg")}
    assert on_disk == {s["file"] for s in manifest["samples"]}
    assert (DATA / "LICENSE").read_text().startswith("MIT License")


def test_checked_in_data_is_under_budget():
    total = sum(p.stat().st_size for p in DATA.iterdir() if p.is_file())
    assert total < SIZE_BUDGET_BYTES, total


def test_every_sample_is_a_1200_by_1600_jpeg(manifest):
    for s in manifest["samples"]:
        image = cv2.imread(str(DATA / s["file"]))
        assert image.shape == (1600, 1200, 3), s["id"]


def _golden(manifest):
    return [(s["id"], s["expected_verdict"]) for s in manifest["samples"] if s["expected_verdict"]]


@pytest.mark.parametrize(
    "sample_id,expected", _golden(json.loads((DATA / "manifest.json").read_text()))
)
def test_golden_verdicts(policy, measure, sample_id, expected):
    if sample_id == "dup_a":
        known = {"clean_a": measure("clean_a").phash}
        record = inspect_file(DATA / "dup_a.jpg", known_hashes=known)
    else:
        record = measure(sample_id)
    verdict = decide(record, policy)
    assert (verdict.outcome, verdict.rule_id) == (expected["outcome"], expected["rule_id"]), (
        verdict.firings
    )


def test_clean_b_is_not_a_duplicate_of_clean_a(policy, measure):
    known = {"clean_a": measure("clean_a").phash}
    record = inspect_file(DATA / "clean_b.jpg", known_hashes=known)
    verdict = decide(record, policy)
    assert verdict.rule_id == "accept"
    assert record.duplicate_of is None


def test_generator_reproduces_the_committed_set(manifest, tmp_path):
    out = tmp_path / "regen"
    subprocess.run(
        [sys.executable, str(ENTRY / "tools" / "make_samples.py"), "--out", str(out)],
        check=True,
        cwd=ENTRY,
        capture_output=True,
    )
    regenerated = json.loads((out / "manifest.json").read_text())
    assert regenerated == manifest
    for s in manifest["samples"]:
        a = cv2.imread(str(DATA / s["file"])).astype(np.int16)
        b = cv2.imread(str(out / s["file"])).astype(np.int16)
        assert a.shape == b.shape
        assert float(np.mean(np.abs(a - b))) < 1.0, s["id"]
