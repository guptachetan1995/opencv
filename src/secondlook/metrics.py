"""The eight measurements, one pure function each. No state, no store, no I/O.

Images are BGR ``uint8`` arrays as ``cv2.imread`` returns them. Every function returns plain
Python numbers, bools, strings and lists so the record that stores them carries no numpy
types and no pixels.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import cv2
import numpy as np

from secondlook.policy import PerceptionConfig
from secondlook.schema import Box

Quad = np.ndarray  # (4, 2) float32, ordered TL, TR, BR, BL, frame pixels

FRAME_QUAD_FRACTION = 0.95  # a 4-gon this large is the frame border, never the page


# ---- 1. document localisation -------------------------------------------------------------


@dataclass(frozen=True)
class Localisation:
    found: bool
    quad: Quad | None
    page_area_fraction: float
    corner_confidence: float
    second_quad_area_fraction: float


def order_quad(points: np.ndarray) -> Quad:
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    sums = pts.sum(axis=1)
    diffs = pts[:, 1] - pts[:, 0]
    return np.array(
        [pts[np.argmin(sums)], pts[np.argmin(diffs)], pts[np.argmax(sums)], pts[np.argmax(diffs)]],
        dtype=np.float32,
    )


def _stretched_gray(bgr: np.ndarray) -> np.ndarray:
    """Gray with its 1st–99th percentile mapped to 0–255, so Canny's thresholds are relative
    to the frame's own dynamic range and a dark frame still yields its paper edge."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    lo, hi = np.percentile(gray, (1, 99))
    if hi - lo < 1:
        return gray
    return cv2.convertScaleAbs(gray, alpha=255.0 / (hi - lo), beta=-lo * 255.0 / (hi - lo))


def _edge_map(bgr: np.ndarray, cfg: PerceptionConfig) -> np.ndarray:
    """Canny edges on a 1-px black-padded frame: a page that runs off the frame still closes
    into a contour along the border, which is what measurement 6 needs to see."""
    gray = cv2.GaussianBlur(_stretched_gray(bgr), (5, 5), 0)
    padded = cv2.copyMakeBorder(gray, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    edges = cv2.Canny(padded, cfg.canny_low, cfg.canny_high)
    return cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)


def _angle_score(quad: Quad) -> float:
    worst = 0.0
    for i in range(4):
        a, b, c = quad[i - 1], quad[i], quad[(i + 1) % 4]
        v1, v2 = a - b, c - b
        cosang = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
        worst = max(worst, abs(angle - 90.0))
    return max(0.0, 1.0 - worst / 90.0)


def _shrink(quad: Quad, px: float) -> Quad:
    centre = quad.mean(axis=0)
    out = quad.copy()
    for i in range(4):
        d = quad[i] - centre
        n = float(np.linalg.norm(d))
        if n > 0:
            out[i] = quad[i] - d / n * px
    return out


def _quad_from_contour(contour: np.ndarray) -> tuple[Quad, float] | None:
    perimeter = cv2.arcLength(contour, True)
    for eps in (0.02, 0.03, 0.05):
        approx = cv2.approxPolyDP(contour, eps * perimeter, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            quad = order_quad(approx.reshape(4, 2))
            contour_area = cv2.contourArea(contour)
            agreement = 1.0 - abs(contour_area - cv2.contourArea(quad)) / max(contour_area, 1.0)
            return quad, max(0.0, min(1.0, agreement)) * _angle_score(quad)
    return None


def _contains_centre(outer: Quad, inner: Quad) -> bool:
    centre = tuple(float(v) for v in inner.mean(axis=0))
    return cv2.pointPolygonTest(outer.reshape(-1, 1, 2), centre, False) >= 0


def _hough_fallback(edges: np.ndarray, shape: tuple[int, ...]) -> Quad | None:
    h, w = shape[:2]
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=80, minLineLength=int(0.25 * min(h, w)), maxLineGap=20
    )
    if lines is None:
        return None
    horizontals, verticals = [], []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1))) % 180
        if angle < 25 or angle > 155:
            horizontals.append((x1, y1, x2, y2))
        elif 65 < angle < 115:
            verticals.append((x1, y1, x2, y2))
    if len(horizontals) < 2 or len(verticals) < 2:
        return None
    top = min(horizontals, key=lambda s: (s[1] + s[3]) / 2)
    bottom = max(horizontals, key=lambda s: (s[1] + s[3]) / 2)
    left = min(verticals, key=lambda s: (s[0] + s[2]) / 2)
    right = max(verticals, key=lambda s: (s[0] + s[2]) / 2)
    if (bottom[1] + bottom[3] - top[1] - top[3]) / 2 < 0.25 * h:
        return None
    if (right[0] + right[2] - left[0] - left[2]) / 2 < 0.25 * w:
        return None
    corners = []
    for a, b in ((top, left), (top, right), (bottom, right), (bottom, left)):
        p = _intersect(a, b)
        if p is None or not (-w * 0.05 <= p[0] <= w * 1.05 and -h * 0.05 <= p[1] <= h * 1.05):
            return None
        corners.append(p)
    return order_quad(np.array(corners, dtype=np.float32))


def _intersect(s1: tuple, s2: tuple) -> tuple[float, float] | None:
    # Cast to Python float before any arithmetic: s1/s2 carry cv2.HoughLinesP's int32
    # coordinates, and the cross-multiplication below overflows a 32-bit accumulator for
    # ordinary phone-photo coordinates (a few thousand pixels) — numpy raises no
    # exception on overflow, it silently wraps, corrupting the detected quad.
    x1, y1, x2, y2 = (float(v) for v in s1)
    x3, y3, x4, y4 = (float(v) for v in s2)
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-6:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    return float(px), float(py)


def locate_document(bgr: np.ndarray, cfg: PerceptionConfig) -> Localisation:
    h, w = bgr.shape[:2]
    frame_area = float(h * w)
    floor = cfg.page_area_floor * frame_area
    ceiling = FRAME_QUAD_FRACTION * frame_area
    edges = _edge_map(bgr, cfg)
    # RETR_LIST, not RETR_EXTERNAL: the padded border closes into a frame-sized contour
    # that would otherwise swallow the page as a child. It is discarded by the ceiling.
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[Quad, float]] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < floor:
            break
        if area >= ceiling:
            continue
        got = _quad_from_contour(contour - 1)  # undo the 1-px padding
        if got is not None:
            candidates.append(got)
    if candidates:
        quad, confidence = candidates[0]
        quad = _shrink(quad, 2.0)  # the dilated edge ring sits ~2 px outside the true edge
        second = 0.0
        for other, _ in candidates[1:]:
            if not _contains_centre(quad, other) and not _contains_centre(other, quad):
                second = float(cv2.contourArea(other)) / frame_area
                break
        return Localisation(
            True, quad, float(cv2.contourArea(quad)) / frame_area, confidence, second
        )
    fallback = _hough_fallback(edges, bgr.shape)
    if fallback is not None and floor <= cv2.contourArea(fallback) < ceiling:
        fallback = fallback - 1
        return Localisation(
            True,
            fallback,
            float(cv2.contourArea(fallback)) / frame_area,
            0.6 * _angle_score(fallback),
            0.0,
        )
    return Localisation(False, None, 0.0, 0.0, 0.0)


def rectify(bgr: np.ndarray, quad: Quad | None, cfg: PerceptionConfig) -> np.ndarray:
    """Warp the quad to a canonical page of ``canonical_page_width``; without a quad, the
    whole frame is scaled to that width so later metrics run at a comparable scale."""
    width = cfg.canonical_page_width
    if quad is None:
        h, w = bgr.shape[:2]
        size = (width, max(8, int(round(h * width / w))))
        return cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)
    tl, tr, br, bl = quad
    span_w = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    span_h = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    height = max(8, int(round(width * span_h / max(span_w, 1.0))))
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    matrix = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    return cv2.warpPerspective(bgr, matrix, (width, height), flags=cv2.INTER_LINEAR)


def normalise_gain(page_gray: np.ndarray) -> np.ndarray:
    """Scale so the 99th percentile sits at 255. A pure gain: sharpness and text presence are
    judged independently of exposure, which measurement 3 reports on the raw page."""
    p99 = float(np.percentile(page_gray, 99))
    if p99 <= 0 or p99 >= 250:
        return page_gray
    return cv2.convertScaleAbs(page_gray, alpha=255.0 / p99, beta=0.0)


def ink_map(page_gray: np.ndarray, cfg: PerceptionConfig) -> tuple[np.ndarray, np.ndarray]:
    """Black-hat darkness against the local paper level, and its Weber contrast in [0, 1].
    Blur spreads ink but conserves its mass; fading removes it — which is what separates
    an out-of-focus receipt (rule 7) from a faded one (rule 1)."""
    k = max(9, (cfg.canonical_page_width // 18) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    paper = cv2.morphologyEx(page_gray, cv2.MORPH_CLOSE, kernel)
    dark = cv2.subtract(paper, page_gray)
    weber = dark.astype(np.float32) / np.maximum(paper.astype(np.float32), 1.0)
    return dark, weber


# ---- 2. focus ------------------------------------------------------------------------------


def focus(
    page_gray: np.ndarray, dark: np.ndarray, cfg: PerceptionConfig
) -> tuple[float, float, list[Box]]:
    """Laplacian variance per unit of ink darkness, per tile. Variance alone scales with how
    much ink a tile holds, so a sparse line-end reads as soft; dividing by mean darkness
    isolates sharpness. Only tiles carrying ink vote (blank paper has no variance whether
    or not it is sharp, and darkness survives blur). ``blur_tiles`` is returned worst-first."""
    cols, rows = cfg.focus_grid
    h, w = page_gray.shape
    lap = cv2.Laplacian(page_gray, cv2.CV_64F)
    inked: list[tuple[float, Box]] = []
    for r in range(rows):
        for c in range(cols):
            y0, y1 = r * h // rows, (r + 1) * h // rows
            x0, x1 = c * w // cols, (c + 1) * w // cols
            if y1 <= y0 or x1 <= x0:
                continue  # a degenerate (extreme-aspect-ratio) page can grid to an empty tile
            ink = float(dark[y0:y1, x0:x1].mean())
            # An empty-tile .mean() is NaN; NaN < threshold is False in Python, so without
            # this guard a broken tile would silently pass through rather than being
            # skipped or flagged — the opposite of "silent accept is the expensive error".
            if not math.isfinite(ink) or ink < cfg.focus_tile_ink_min:
                continue
            tile_variance = float(lap[y0:y1, x0:x1].var())
            if not math.isfinite(tile_variance):
                continue
            inked.append((tile_variance / ink, [x0, y0, x1 - x0, y1 - y0]))
    inked.sort(key=lambda t: t[0])
    focus_min = inked[0][0] if inked else 0.0
    blur = [box for v, box in inked if v < cfg.blur_tile_threshold]
    page_ink = max(float(dark.mean()), 1e-6)
    return float(lap.var()) / page_ink, focus_min, blur


# ---- 3. exposure ---------------------------------------------------------------------------


def exposure(page_gray: np.ndarray, cfg: PerceptionConfig) -> tuple[float, float, float]:
    hist = cv2.calcHist([page_gray], [0], None, [256], [0, 256]).ravel()
    total = float(hist.sum())
    cdf = np.cumsum(hist) / total
    p5 = int(np.searchsorted(cdf, 0.05))
    p95 = int(np.searchsorted(cdf, 0.95))
    low = float(hist[: cfg.exposure_low_level + 1].sum() / total)
    high = float(hist[cfg.exposure_high_level :].sum() / total)
    return low, high, float(p95 - p5)


# ---- 5. text presence (classical path) -----------------------------------------------------


def text_regions(
    dark: np.ndarray, weber: np.ndarray, cfg: PerceptionConfig
) -> tuple[list[Box], float, float, bool]:
    """Ink with enough Weber contrast, closed horizontally into word boxes. Returns
    (boxes, coverage_fraction, median_height, bottom_band_has_text)."""
    h, w = dark.shape
    inset = max(2, int(round(0.015 * w)))
    mask = np.zeros((h, w), np.uint8)
    core = (weber >= cfg.text_contrast_min) & (dark >= cfg.text_darkness_min)
    mask[inset : h - inset, inset : w - inset] = core[inset : h - inset, inset : w - inset]
    mask *= 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, w // 32), 3))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    count, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    boxes: list[Box] = []
    for i in range(1, count):
        x, y, bw, bh, _ = (int(v) for v in stats[i])
        if not (cfg.text_min_height_px <= bh <= cfg.text_max_height_px):
            continue
        if bw < 0.8 * bh or bw * bh < 30:
            continue
        boxes.append([x, y, bw, bh])
    boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
    boxes = boxes[: cfg.text_boxes_cap]
    boxes.sort(key=lambda b: (b[1], b[0]))
    coverage = sum(b[2] * b[3] for b in boxes) / float(h * w)
    median_h = float(np.median([b[3] for b in boxes])) if boxes else 0.0
    band_top = h * (1.0 - cfg.bottom_band_fraction)
    bottom = any(b[1] + b[3] / 2.0 >= band_top for b in boxes)
    return boxes, float(coverage), median_h, bool(bottom)


def line_bands(boxes: list[Box]) -> list[Box]:
    """Group word boxes that overlap vertically into text lines, each spanning from its
    leftmost to its rightmost word — so a burnt-out total still sits inside its line."""
    bands: list[Box] = []
    for x, y, w, h in sorted(boxes, key=lambda b: b[1]):
        for band in bands:
            by, bh = band[1], band[3]
            overlap = min(y + h, by + bh) - max(y, by)
            if overlap > 0.5 * min(h, bh):
                x0, y0 = min(band[0], x), min(by, y)
                x1, y1 = max(band[0] + band[2], x + w), max(by + bh, y + h)
                band[:] = [x0, y0, x1 - x0, y1 - y0]
                break
        else:
            bands.append([x, y, w, h])
    return bands


def dnn_engine_name() -> str:
    """Which DNN engine OpenCV 5 would pick for the optional detector path: the classic one
    when ``OPENCV_FORCE_DNN_ENGINE`` says so, otherwise the new engine ``readNet`` tries first."""
    forced = os.environ.get("OPENCV_FORCE_DNN_ENGINE", "").strip().lower()
    return "classic" if forced in {"classic", str(int(cv2.dnn.ENGINE_CLASSIC))} else "new"


# ---- 4. glare ------------------------------------------------------------------------------


def glare(
    page_bgr: np.ndarray, text_boxes: list[Box], text_median_height: float, cfg: PerceptionConfig
) -> tuple[float, list[Box], float]:
    h, w = page_bgr.shape[:2]
    page_area = float(h * w)
    hsv = cv2.cvtColor(page_bgr, cv2.COLOR_BGR2HSV)
    mask: np.ndarray = (hsv[..., 1] <= cfg.glare_saturation_max) & (
        hsv[..., 2] >= cfg.glare_value_min
    )
    mask8 = mask.astype(np.uint8) * 255
    kernel = np.ones((5, 5), np.uint8)
    mask8 = cv2.morphologyEx(mask8, cv2.MORPH_OPEN, kernel)
    mask8 = cv2.morphologyEx(mask8, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask8, connectivity=8)
    kept = np.zeros((h, w), dtype=bool)
    boxes: list[Box] = []
    for i in range(1, count):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        fraction = area / page_area
        if fraction < cfg.glare_min_area_fraction or fraction > cfg.glare_max_area_fraction:
            continue
        kept |= labels == i
        boxes.append([x, y, bw, bh])
    glare_pixels = int(kept.sum())
    if glare_pixels == 0:
        return 0.0, [], 0.0
    block = np.zeros((h, w), dtype=np.uint8)
    pad = int(round(1.5 * text_median_height))
    for x, y, bw, bh in line_bands(text_boxes):
        cv2.rectangle(block, (x - pad, y - pad), (x + bw + pad, y + bh + pad), 255, -1)
    over = int((kept & (block > 0)).sum()) / glare_pixels
    return glare_pixels / page_area, boxes, float(over)


# ---- 6. frame-edge crop --------------------------------------------------------------------


def edge_touch(
    quad: Quad | None, image_shape: tuple[int, ...], cfg: PerceptionConfig
) -> list[str]:
    if quad is None:
        return []
    h, w = image_shape[:2]
    mx, my = cfg.edge_touch_margin_fraction * w, cfg.edge_touch_margin_fraction * h
    tl, tr, br, bl = quad
    sides = []
    if tl[1] <= my and tr[1] <= my:
        sides.append("top")
    if bl[1] >= h - 1 - my and br[1] >= h - 1 - my:
        sides.append("bottom")
    if tl[0] <= mx and bl[0] <= mx:
        sides.append("left")
    if tr[0] >= w - 1 - mx and br[0] >= w - 1 - mx:
        sides.append("right")
    return sides


# ---- 7. machine-readable code --------------------------------------------------------------


def machine_code(page_bgr: np.ndarray) -> tuple[str | None, bool]:
    """Kind and whether it decoded. The payload is read and discarded here; it never leaves."""
    text, points, _ = cv2.QRCodeDetector().detectAndDecode(page_bgr)
    if text:
        return "qr", True
    if points is not None and len(points):
        return "qr", False
    text, points, _ = cv2.barcode_BarcodeDetector().detectAndDecode(page_bgr)
    if text:
        return "barcode", True
    if points is not None and len(points):
        return "barcode", False
    return None, False


# ---- 8. duplicate --------------------------------------------------------------------------


def dhash(page_gray: np.ndarray) -> str:
    small = cv2.resize(page_gray, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (small[:, 1:] > small[:, :-1]).ravel()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def nearest(phash: str, known: dict[str, str] | None, threshold: int) -> tuple[int, str | None]:
    """Hamming distance to the closest hash in the open batch; 64 when the batch is empty."""
    if not known:
        return 64, None
    best_id, best = min(known.items(), key=lambda kv: hamming(phash, kv[1]))
    distance = hamming(phash, best)
    return distance, best_id if distance <= threshold else None
