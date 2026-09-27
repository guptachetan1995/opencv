"""Metrics: property assertions with tolerances against the synthetic set's
ground truth. There are no stored pixel baselines anywhere in this suite, because OpenCV
5's warping numerics differ from 4.x and a 4.x-era baseline would lie in either direction."""

from __future__ import annotations

import math

import cv2
import numpy as np
import pytest

from conftest import DATA
from secondlook import metrics


def _corner_error(measured: list[list[int]], truth: list[list[float]]) -> float:
    return max(math.dist(m, t) for m, t in zip(measured, truth, strict=True))


# ---- 1. localisation and rectification ---------------------------------------------------


@pytest.mark.parametrize("sample", ["clean_a", "clean_b", "warp", "dup_a", "glare_text"])
def test_detected_quad_lands_on_the_ground_truth_corners(measure, samples, sample):
    m = measure(sample)
    assert m.quad_found and m.corner_confidence >= 0.8
    assert _corner_error(m.quad, samples[sample]["corners"]) <= 8.0, m.quad


def test_strong_keystone_still_rectifies(measure, samples):
    m = measure("warp")
    assert _corner_error(m.quad, samples["warp"]["corners"]) <= 8.0
    assert m.edge_touch_sides == []
    assert m.text_coverage_fraction > 0.1  # the page is upright and readable after the warp


def test_intersect_does_not_overflow_on_realistic_photo_coordinates():
    """cv2.HoughLinesP returns int32 coordinates; the cross-multiplication in _intersect
    overflows a 32-bit accumulator well within ordinary phone-photo dimensions (here, a
    4000x4000 frame), silently wrapping to a wrong point instead of raising."""
    s1 = (np.int32(0), np.int32(0), np.int32(4000), np.int32(4000))  # main diagonal
    s2 = (np.int32(0), np.int32(4000), np.int32(4000), np.int32(0))  # anti-diagonal
    point = metrics._intersect(s1, s2)
    assert point is not None
    assert point == pytest.approx((2000.0, 2000.0))


def test_no_quad_on_a_bare_table(measure):
    m = measure("not_doc")
    assert m.quad_found is False and m.quad is None
    assert m.page_area_fraction == 0.0 and m.corner_confidence == 0.0


def test_two_receipts_yield_a_second_quad(measure):
    m = measure("two_docs")
    assert m.quad_found
    assert m.second_quad_area_fraction > 0.06
    for sample in ("clean_a", "clean_b", "warp", "crop_bottom"):
        assert measure(sample).second_quad_area_fraction == 0.0


def test_rectify_round_trips_a_known_warp(policy):
    """A page warped by known corner offsets rectifies back to its own geometry."""
    cfg = policy.perception
    paper = np.full((700, 400, 3), 230, np.uint8)
    cv2.putText(paper, "TOTAL 12.50", (40, 350), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 3)
    src = np.array([[0, 0], [399, 0], [399, 699], [0, 699]], np.float32)
    quad = np.array([[210, 130], [560, 90], [610, 820], [150, 780]], np.float32)
    frame = np.full((1000, 800, 3), 80, np.uint8)
    warped = cv2.warpPerspective(paper, cv2.getPerspectiveTransform(src, quad), (800, 1000))
    mask = cv2.warpPerspective(
        np.full((700, 400), 255, np.uint8), cv2.getPerspectiveTransform(src, quad), (800, 1000)
    )
    frame[mask > 0] = warped[mask > 0]
    loc = metrics.locate_document(frame, cfg)
    assert loc.found
    assert _corner_error(loc.quad.tolist(), quad.tolist()) <= 6.0
    page = metrics.rectify(frame, loc.quad, cfg)
    assert page.shape[1] == cfg.canonical_page_width
    # rectify sizes the page from the quad's longest spans, so that is the aspect to expect
    expected_aspect = max(math.dist(quad[0], quad[3]), math.dist(quad[1], quad[2])) / max(
        math.dist(quad[0], quad[1]), math.dist(quad[3], quad[2])
    )
    assert abs(page.shape[0] / page.shape[1] - expected_aspect) < 0.03
    back = cv2.resize(page, (400, 700), interpolation=cv2.INTER_AREA)
    assert np.mean(np.abs(back.astype(int) - paper.astype(int))) < 12.0


# ---- 2. focus ------------------------------------------------------------------------------


def test_focus_falls_monotonically_with_the_applied_sigma(measure):
    series = [measure(s) for s in ("clean_a", "blur_1", "blur_2", "blur_4")]
    globals_ = [m.focus_global for m in series]
    assert globals_ == sorted(globals_, reverse=True), globals_
    assert globals_[0] > 4 * globals_[-1]
    minima = [m.focus_min_tile for m in series]
    assert minima[0] > minima[-1]


def test_focus_never_returns_nan_when_the_grid_has_more_rows_than_the_page_has_pixels(policy):
    """rectify() floors the rectified page at 8 px tall; if focus_grid's row count is ever
    configured above that, naive tile slicing produces an empty tile and an empty-slice
    .mean() is NaN, which then compares False against every threshold and would let a
    broken measurement pass silently instead of being skipped or flagged."""
    import math
    from dataclasses import replace

    cfg = replace(policy.perception, focus_grid=(policy.perception.focus_grid[0], 12))
    page_gray = np.full((8, cfg.canonical_page_width), 200, np.uint8)
    dark = np.zeros((8, cfg.canonical_page_width), np.float32)
    focus_global, focus_min_tile, _blur = metrics.focus(page_gray, dark, cfg)
    assert math.isfinite(focus_global)
    assert math.isfinite(focus_min_tile)


def test_partial_blur_is_localised_to_the_blurred_band(measure, samples):
    m = measure("blur_bottom")
    start = samples["blur_bottom"]["params"]["from_fraction"]
    page_h = m.page_shape[0]
    assert m.blur_tiles, "the blurred band must produce blur tiles"
    for _x, y, _w, _h in m.blur_tiles:
        assert y >= start * page_h - 2, (y, start * page_h)
    assert measure("clean_a").blur_tiles == []


# ---- 3. exposure ---------------------------------------------------------------------------


def test_exposure_fractions(measure):
    assert measure("under").clipped_low_frac > 0.8
    assert measure("over").clipped_high_frac > 0.6
    clean = measure("clean_a")
    assert clean.clipped_low_frac < 0.05 and clean.clipped_high_frac < 0.05
    assert clean.contrast_p95_p5 > 40


# ---- 4. glare ------------------------------------------------------------------------------


@pytest.mark.parametrize("sample", ["glare_text", "glare_white"])
def test_glare_area_is_within_15_percent_of_the_applied_ellipse(measure, samples, sample):
    m = measure(sample)
    truth = samples[sample]["params"]["area_fraction"]
    assert abs(m.glare_area_fraction - truth) <= 0.15 * truth, (m.glare_area_fraction, truth)
    assert len(m.glare_boxes) == 1


def test_glare_over_text_separates_the_total_from_white_space(measure, policy):
    threshold = next(r for r in policy.rules if r["id"] == "glare_over_total")["clauses"][0][
        "value"
    ]
    assert measure("glare_text").glare_over_text_frac > threshold
    assert measure("glare_white").glare_over_text_frac < 0.1
    assert measure("clean_a").glare_area_fraction == 0.0


def test_glare_box_covers_the_total_line(measure, samples):
    m = measure("glare_text")
    ((x, y, w, h),) = m.glare_boxes
    centre = samples["glare_text"]["params"]["centre"]
    paper_w, paper_h = samples["glare_text"]["paper_size"]
    scale = m.page_shape[1] / paper_w
    assert x <= centre[0] * scale <= x + w
    assert y <= centre[1] * scale * (m.page_shape[0] / (paper_h * scale)) <= y + h


# ---- 5. text -------------------------------------------------------------------------------


def test_text_coverage_survives_blur_but_not_fading(measure):
    assert measure("blur_4").text_coverage_fraction > 0.1
    assert measure("clean_a").text_coverage_fraction > 0.1
    assert measure("faded").text_coverage_fraction < 0.005
    assert measure("faded").text_box_count == 0


def test_bottom_band_has_text_only_when_the_page_is_cut_inside_the_text(measure):
    assert measure("crop_bottom").bottom_band_has_text is True
    assert measure("clean_a").bottom_band_has_text is False
    assert measure("clean_b").bottom_band_has_text is False


# ---- 6. frame-edge crop --------------------------------------------------------------------


def test_edge_touch_reports_exactly_the_clipped_side(measure, samples):
    assert measure("crop_bottom").edge_touch_sides == [samples["crop_bottom"]["params"]["side"]]
    for sample in ("clean_a", "clean_b", "warp", "glare_text", "dup_a", "two_docs"):
        assert measure(sample).edge_touch_sides == [], sample


# ---- 7. machine-readable code --------------------------------------------------------------


def test_qr_decodes_only_where_one_was_printed(measure):
    soft = measure("qr_soft")
    assert (soft.code_kind, soft.code_decoded) == ("qr", True)
    for sample in ("clean_a", "clean_b", "glare_text"):
        assert (measure(sample).code_kind, measure(sample).code_decoded) == (None, False)


# ---- 8. duplicate --------------------------------------------------------------------------


def test_dhash_distances(measure, policy):
    threshold = policy.perception.duplicate_hamming_threshold
    a, b, again = measure("clean_a"), measure("clean_b"), measure("dup_a")
    assert metrics.hamming(a.phash, a.phash) == 0
    assert metrics.hamming(a.phash, again.phash) <= threshold
    assert metrics.hamming(a.phash, b.phash) > threshold + 1


def test_nearest_names_the_duplicate_and_ignores_strangers(measure, policy):
    threshold = policy.perception.duplicate_hamming_threshold
    a = measure("clean_a").phash
    known = {"c_first": a, "c_other": measure("clean_b").phash}
    distance, who = metrics.nearest(measure("dup_a").phash, known, threshold)
    assert who == "c_first" and distance <= threshold
    distance, who = metrics.nearest(measure("clean_b").phash, {"c_first": a}, threshold)
    assert who is None and distance > threshold
    assert metrics.nearest(a, None, threshold) == (64, None)


def test_inspect_is_deterministic(measure):
    from secondlook import inspect_file

    first = inspect_file(DATA / "glare_text.jpg")
    second = inspect_file(DATA / "glare_text.jpg")
    assert first.to_dict() | {"elapsed_ms": {}} == second.to_dict() | {"elapsed_ms": {}}


def test_undecodable_file_raises_valueerror_not_filenotfounderror(tmp_path):
    """The file exists (the caller just wrote it) — it just isn't decodable image data.
    app/server.py and deploy/handler.py both turn ValueError into a clean 409; the wrong
    exception type here previously fell through to a bare, uncaught 500."""
    from secondlook import inspect_file

    garbage = tmp_path / "not_an_image.jpg"
    garbage.write_bytes(b"this is not jpeg data")
    with pytest.raises(ValueError, match="could not decode"):
        inspect_file(garbage)


def test_oversized_decoded_image_is_refused_before_the_pipeline_runs(tmp_path):
    """Compressed byte size (the HTTP layer's MAX_BODY_BYTES) says nothing about decoded
    pixel count — a small, highly-compressed image can still decode to a huge array and
    run the full measurement pipeline at that resolution."""
    from secondlook import inspect_file
    from secondlook.perception import MAX_DECODED_PIXELS

    huge = np.zeros((8000, 8000, 3), np.uint8)
    assert huge.shape[0] * huge.shape[1] > MAX_DECODED_PIXELS
    path = tmp_path / "huge.jpg"
    cv2.imwrite(str(path), huge)
    with pytest.raises(ValueError, match="pixel"):
        inspect_file(path)
