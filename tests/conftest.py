from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from pathlib import Path

import pytest

from secondlook import Measurements, Policy, inspect_file, load_policy

ENTRY = Path(__file__).resolve().parent.parent
DATA = ENTRY / "data" / "synthetic"


@pytest.fixture(scope="session")
def policy() -> Policy:
    return load_policy()


@pytest.fixture(scope="session")
def manifest() -> dict:
    return json.loads((DATA / "manifest.json").read_text())


@pytest.fixture(scope="session")
def samples(manifest) -> dict[str, dict]:
    return {s["id"]: s for s in manifest["samples"]}


@cache
def _measure(sample_id: str) -> Measurements:
    return inspect_file(DATA / f"{sample_id}.jpg")


@pytest.fixture(scope="session")
def measure():
    """Measure a sample by id, memoised across the session (each call is ~0.3 s)."""
    return _measure


def clean_measurements() -> Measurements:
    """An in-code record that lands on `accept`: every metric comfortably inside its band.
    Policy tests mutate one field at a time with ``dataclasses.replace``."""
    return Measurements(
        image_shape=[1600, 1200],
        page_shape=[1650, 800],
        quad_found=True,
        quad=[[360, 250], [868, 260], [855, 1355], [325, 1342]],
        page_area_fraction=0.3,
        corner_confidence=0.98,
        second_quad_area_fraction=0.0,
        focus_global=30.0,
        focus_min_tile=12.0,
        blur_tiles=[],
        clipped_low_frac=0.01,
        clipped_high_frac=0.0,
        contrast_p95_p5=80.0,
        glare_area_fraction=0.0,
        glare_boxes=[],
        glare_over_text_frac=0.0,
        text_box_count=38,
        text_coverage_fraction=0.17,
        text_median_height_px=26.0,
        bottom_band_has_text=False,
        text_boxes=[[40, 60, 300, 30], [40, 110, 200, 26]],
        edge_touch_sides=[],
        code_kind=None,
        code_decoded=False,
        phash="0123456789abcdef",
        nearest_distance=64,
        duplicate_of=None,
        opencv_version="5.0.0",
        dnn_engine="new",
        text_detector="classical",
        elapsed_ms={"localise": 10.0},
    )


def with_fields(**fields) -> Measurements:
    return replace(clean_measurements(), **fields)
