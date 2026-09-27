"""The structured-result schema: regions, quality flags and confidences, with the type
contract the README promises — no pixel data and no decoded text, ever."""

from __future__ import annotations

import json
from dataclasses import fields

from secondlook import Measurements
from secondlook.schema import CONFIDENCE_FIELDS, FLAG_FIELDS, REGION_FIELDS

GOLDEN_FIELDS = [
    "image_shape",
    "page_shape",
    "quad_found",
    "quad",
    "page_area_fraction",
    "corner_confidence",
    "second_quad_area_fraction",
    "focus_global",
    "focus_min_tile",
    "blur_tiles",
    "clipped_low_frac",
    "clipped_high_frac",
    "contrast_p95_p5",
    "glare_area_fraction",
    "glare_boxes",
    "glare_over_text_frac",
    "text_box_count",
    "text_coverage_fraction",
    "text_median_height_px",
    "bottom_band_has_text",
    "text_boxes",
    "edge_touch_sides",
    "code_kind",
    "code_decoded",
    "phash",
    "nearest_distance",
    "duplicate_of",
    "opencv_version",
    "dnn_engine",
    "text_detector",
    "elapsed_ms",
]


def _is_box(value, page_h: int, page_w: int) -> bool:
    if not (isinstance(value, list) and len(value) == 4):
        return False
    x, y, w, h = value
    if not all(type(v) is int for v in value):
        return False
    return (
        0 <= x < page_w
        and 0 <= y < page_h
        and w > 0
        and h > 0
        and x + w <= page_w
        and y + h <= page_h
    )


def test_golden_field_set_is_exactly_the_spec(measure):
    record = measure("clean_a").to_dict()
    assert list(record) == GOLDEN_FIELDS
    assert [f.name for f in fields(Measurements)] == GOLDEN_FIELDS
    assert set(REGION_FIELDS) | set(FLAG_FIELDS) | set(CONFIDENCE_FIELDS) <= set(GOLDEN_FIELDS)


def test_regions_are_in_bounds_int_boxes(measure):
    for sample in ("clean_a", "glare_text", "blur_bottom", "crop_bottom", "two_docs"):
        m = measure(sample)
        page_h, page_w = m.page_shape
        img_h, img_w = m.image_shape
        for name in ("blur_tiles", "glare_boxes", "text_boxes"):
            for box in getattr(m, name):
                assert _is_box(box, page_h, page_w), (sample, name, box)
        assert m.quad is not None and len(m.quad) == 4
        for x, y in m.quad:
            assert type(x) is int and type(y) is int
            assert -2 <= x <= img_w + 1 and -2 <= y <= img_h + 1


def test_quality_flags_are_bools_or_side_names(measure):
    m = measure("crop_bottom")
    for name in ("quad_found", "bottom_band_has_text", "code_decoded"):
        assert type(getattr(m, name)) is bool, name
    assert isinstance(m.edge_touch_sides, list)
    assert set(m.edge_touch_sides) <= {"top", "bottom", "left", "right"}


def test_confidences_and_fractions_are_unit_floats(measure):
    m = measure("glare_text")
    for name in CONFIDENCE_FIELDS:
        value = getattr(m, name)
        assert type(value) is float and 0.0 <= value <= 1.0, (name, value)
    assert type(m.focus_global) is float and m.focus_global >= 0
    assert type(m.focus_min_tile) is float and m.focus_min_tile >= 0
    assert type(m.contrast_p95_p5) is float
    assert type(m.text_box_count) is int and m.text_box_count == len(m.text_boxes)
    assert type(m.nearest_distance) is int and 0 <= m.nearest_distance <= 64
    assert len(m.phash) == 16 and int(m.phash, 16) >= 0


def test_no_pixels_and_no_text_ever_reach_the_record(measure):
    m = measure("qr_soft")
    assert m.code_kind == "qr" and m.code_decoded is True
    record = m.to_dict()
    strings = [v for v in _leaves(record) if isinstance(v, str)]
    # The only strings are enums, the hash and the version: never a decoded payload.
    assert all(len(s) <= 16 for s in strings), strings
    assert all(isinstance(v, (int, float, bool, str, type(None))) for v in _leaves(record))


def test_json_round_trip_is_lossless(measure):
    m = measure("clean_a")
    encoded = json.dumps(m.to_dict(), sort_keys=True)
    assert len(encoded) < 20_000
    assert Measurements.from_dict(json.loads(encoded)) == m


def test_provenance_fields(measure):
    m = measure("clean_a")
    assert m.dnn_engine in ("new", "classic")
    assert m.text_detector in ("classical", "dnn")
    assert set(m.elapsed_ms) == {
        "localise",
        "focus",
        "exposure",
        "text",
        "glare",
        "edge",
        "code",
        "duplicate",
    }
    assert all(type(v) is float and v >= 0 for v in m.elapsed_ms.values())
    assert m.image_shape == [1600, 1200]
    assert m.page_shape[1] == 800


def _leaves(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _leaves(v)
    elif isinstance(value, list):
        for v in value:
            yield from _leaves(v)
    else:
        yield value
