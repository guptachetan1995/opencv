"""Orchestrates the eight measurements into one ``Measurements`` record.

Rectification runs first; every later measurement reads the rectified page, which is why
blur and glare are reported by location on the receipt rather than as one score for the
photograph. Running ``inspect`` twice on the same image yields the same record.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from secondlook import metrics
from secondlook.policy import Policy, load_policy
from secondlook.schema import Measurements

TEXT_DETECTOR = "classical"  # the DNN text-detector path is not built; no weights are vendored

# A generous ceiling on decoded pixel count, not compressed byte size: the HTTP layer's
# MAX_BODY_BYTES already caps the upload, but a small, highly-compressed JPEG can still
# decode to a huge array and run the full pipeline at that resolution before anything
# else notices. 50 MP comfortably exceeds any real phone camera's output.
MAX_DECODED_PIXELS = 50_000_000


def inspect(
    bgr: np.ndarray,
    *,
    known_hashes: dict[str, str] | None = None,
    policy: Policy | None = None,
) -> Measurements:
    """Measure one BGR frame. ``known_hashes`` maps capture ids of the open batch to their
    ``phash`` so measurement 8 can name a suspected duplicate."""
    cfg = (policy or load_policy()).perception
    elapsed: dict[str, float] = {}

    tick = perf_counter()
    loc = metrics.locate_document(bgr, cfg)
    page = metrics.rectify(bgr, loc.quad, cfg)
    page_gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
    gray_norm = metrics.normalise_gain(page_gray)
    dark, weber = metrics.ink_map(gray_norm, cfg)
    elapsed["localise"] = _ms(tick)

    tick = perf_counter()
    focus_global, focus_min_tile, blur_tiles = metrics.focus(gray_norm, dark, cfg)
    elapsed["focus"] = _ms(tick)

    tick = perf_counter()
    clipped_low, clipped_high, contrast = metrics.exposure(page_gray, cfg)
    elapsed["exposure"] = _ms(tick)

    tick = perf_counter()
    text_boxes, coverage, median_h, bottom_has_text = metrics.text_regions(dark, weber, cfg)
    elapsed["text"] = _ms(tick)

    tick = perf_counter()
    glare_fraction, glare_boxes, glare_over_text = metrics.glare(page, text_boxes, median_h, cfg)
    elapsed["glare"] = _ms(tick)

    tick = perf_counter()
    sides = metrics.edge_touch(loc.quad, bgr.shape, cfg)
    elapsed["edge"] = _ms(tick)

    tick = perf_counter()
    code_kind, code_decoded = metrics.machine_code(page)
    elapsed["code"] = _ms(tick)

    tick = perf_counter()
    phash = metrics.dhash(page_gray)
    distance, duplicate_of = metrics.nearest(phash, known_hashes, cfg.duplicate_hamming_threshold)
    elapsed["duplicate"] = _ms(tick)

    return Measurements(
        image_shape=[int(bgr.shape[0]), int(bgr.shape[1])],
        page_shape=[int(page.shape[0]), int(page.shape[1])],
        quad_found=loc.found,
        quad=[[int(round(x)), int(round(y))] for x, y in loc.quad]
        if loc.quad is not None
        else None,
        page_area_fraction=_unit(loc.page_area_fraction),
        corner_confidence=_unit(loc.corner_confidence),
        second_quad_area_fraction=_unit(loc.second_quad_area_fraction),
        focus_global=round(focus_global, 3),
        focus_min_tile=round(focus_min_tile, 3),
        blur_tiles=blur_tiles,
        clipped_low_frac=_unit(clipped_low),
        clipped_high_frac=_unit(clipped_high),
        contrast_p95_p5=float(contrast),
        glare_area_fraction=_unit(glare_fraction),
        glare_boxes=glare_boxes,
        glare_over_text_frac=_unit(glare_over_text),
        text_box_count=len(text_boxes),
        text_coverage_fraction=_unit(coverage),
        text_median_height_px=round(median_h, 1),
        bottom_band_has_text=bottom_has_text,
        text_boxes=text_boxes,
        edge_touch_sides=sides,
        code_kind=code_kind,
        code_decoded=code_decoded,
        phash=phash,
        nearest_distance=distance,
        duplicate_of=duplicate_of,
        opencv_version=cv2.__version__,
        dnn_engine=metrics.dnn_engine_name(),
        text_detector=TEXT_DETECTOR,
        elapsed_ms=elapsed,
    )


def inspect_file(path: str | Path, **kwargs) -> Measurements:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        # ValueError, not FileNotFoundError: the file exists (the caller just wrote it),
        # it just isn't decodable image data. Both app/server.py and deploy/handler.py
        # already turn a ValueError into a clean 409 "the request is invalid" response —
        # raising the wrong exception type here previously fell through to a bare 500.
        raise ValueError(f"could not decode an image at {path}")
    pixels = bgr.shape[0] * bgr.shape[1]
    if pixels > MAX_DECODED_PIXELS:
        raise ValueError(
            f"decoded image is {pixels:,} pixels, over the {MAX_DECODED_PIXELS:,}-pixel cap"
        )
    return inspect(bgr, **kwargs)


def _ms(since: float) -> float:
    return round((perf_counter() - since) * 1000.0, 2)


def _unit(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)
