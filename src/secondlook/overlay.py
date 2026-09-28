"""The evidence overlay: the photo with every region the measurements located drawn on it.

Rendered on request from the photo plus its ``Measurements`` and ``Verdict`` and returned
as image bytes; nothing here writes to a store. The records stay pixel-free
(``schema.py``); the overlay exists only while someone is looking at it.

Two panels side by side. On the left, the frame as posted, with the document quad that
measurement 1 located. On the right, the rectified page every other measurement ran on,
with the text boxes (measurement 5), the blur tiles (2), the glare boxes (4) and the
verdict's hint box. A header names the verdict and the clause that fired it, with the
measured value against its threshold, read from ``verdict.firings``.

The page is re-warped from the stored ``quad`` onto exactly ``page_shape``, so every
page-space box lands where the measurement found it. Drawing uses OpenCV only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from secondlook.schema import Measurements, Verdict

# BGR
QUAD = (60, 170, 60)
TEXT = (205, 140, 40)
BLUR = (0, 140, 255)
GLARE = (200, 40, 200)
HINT = (40, 40, 225)
INK = (30, 30, 30)
PAPER = (250, 250, 250)
OUTCOME = {"accept": (50, 140, 50), "retake": (0, 120, 220), "escalate": (50, 50, 200)}

FONT = cv2.FONT_HERSHEY_SIMPLEX


def rectified_page(bgr: np.ndarray, m: Measurements) -> np.ndarray:
    """The page the measurements read, rebuilt from the stored quad."""
    h, w = m.page_shape
    if m.quad is None:
        return cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
    src = np.array(m.quad, dtype=np.float32)
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(bgr, matrix, (w, h), flags=cv2.INTER_LINEAR)


def annotate_page(bgr: np.ndarray, m: Measurements, v: Verdict | None) -> np.ndarray:
    page = rectified_page(bgr, m)
    fill = page.copy()
    for x, y, w, h in m.blur_tiles:
        cv2.rectangle(fill, (x, y), (x + w, y + h), BLUR, -1)
    for x, y, w, h in m.glare_boxes:
        cv2.rectangle(fill, (x, y), (x + w, y + h), GLARE, -1)
    page = cv2.addWeighted(fill, 0.3, page, 0.7, 0)
    for x, y, w, h in m.text_boxes:
        cv2.rectangle(page, (x, y), (x + w, y + h), TEXT, 1)
    for x, y, w, h in m.blur_tiles:
        cv2.rectangle(page, (x, y), (x + w, y + h), BLUR, 2)
    for x, y, w, h in m.glare_boxes:
        cv2.rectangle(page, (x, y), (x + w, y + h), GLARE, 3)
    if v is not None and v.hint_box is not None:
        x, y, w, h = v.hint_box
        cv2.rectangle(page, (x, y), (x + w - 1, y + h - 1), HINT, 6)
        label = f"hint: {v.rule_id}"
        _label(page, label, (x + 6, max(y - 10, 24)), HINT)
    return page


def annotate_frame(bgr: np.ndarray, m: Measurements) -> np.ndarray:
    frame = bgr.copy()
    thickness = max(3, frame.shape[1] // 250)
    if m.quad is not None:
        pts = np.array(m.quad, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(frame, [pts], True, QUAD, thickness)
    else:
        _label(frame, "no document quad found", (24, 60), HINT, scale=1.4)
    for side in m.edge_touch_sides:
        h, w = frame.shape[:2]
        edge = {
            "top": ((0, 0), (w - 1, 0)),
            "bottom": ((0, h - 1), (w - 1, h - 1)),
            "left": ((0, 0), (0, h - 1)),
            "right": ((w - 1, 0), (w - 1, h - 1)),
        }[side]
        cv2.line(frame, edge[0], edge[1], HINT, thickness * 3)
    return frame


def headline(v: Verdict | None) -> list[str]:
    """The header lines: outcome and rule, then the clause(s) that fired, then the
    instruction a person sees. Everything comes from the verdict record."""
    if v is None:
        return ["NOT DECIDED YET", "measured, no verdict recorded"]
    lines = [f"{v.outcome.upper()}  {v.rule_id}"]
    fired = [f for f in v.firings if f.rule_id == v.rule_id and f.matched]
    if fired:
        lines.append(
            "  |  ".join(_clause(f.metric, f.value, f.comparison, f.threshold) for f in fired)
        )
    elif v.outcome == "accept":
        lines.append("no rule above accept matched")
    lines.append(v.reason_text)
    return [_ascii(line) for line in lines]


def render(
    bgr: np.ndarray, m: Measurements, v: Verdict | None, *, frame: bool = True
) -> np.ndarray:
    """The full overlay: a header over the frame panel (optional) and the page panel."""
    page = annotate_page(bgr, m, v)
    panels = [page]
    if frame:
        framed = annotate_frame(bgr, m)
        scale = page.shape[0] / framed.shape[0]
        framed = cv2.resize(
            framed,
            (int(round(framed.shape[1] * scale)), page.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
        panels = [framed, page]
    captions = ["rectified page" if m.quad is not None else "no quad: the whole frame, scaled"]
    if frame:
        captions.insert(0, "as posted")
    gap, caption_h = 24, 44
    body_w = sum(p.shape[1] for p in panels) + gap * (len(panels) + 1)
    body_h = caption_h + page.shape[0] + gap
    body = np.full((body_h, body_w, 3), PAPER, dtype=np.uint8)
    x = gap
    for panel, caption in zip(panels, captions, strict=True):
        cv2.putText(body, caption, (x, caption_h - 14), FONT, 0.8, INK, 2, cv2.LINE_AA)
        body[caption_h : caption_h + panel.shape[0], x : x + panel.shape[1]] = panel
        x += panel.shape[1] + gap
    header = header_band(headline(v), body_w, OUTCOME.get(v.outcome if v else "", INK))
    legend = legend_band(body_w, quad=frame)
    return np.vstack([header, body, legend])


def render_jpeg(
    image_path: str | Path,
    m: Measurements,
    v: Verdict | None,
    *,
    frame: bool = True,
    max_width: int = 1400,
    quality: int = 85,
) -> bytes:
    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("could not decode the held photo")  # no server path in an HTTP body
    return encode_jpeg(render(bgr, m, v, frame=frame), max_width=max_width, quality=quality)


def encode_jpeg(image: np.ndarray, *, max_width: int = 1400, quality: int = 85) -> bytes:
    if image.shape[1] > max_width:
        scale = max_width / image.shape[1]
        image = cv2.resize(
            image, (max_width, int(round(image.shape[0] * scale))), interpolation=cv2.INTER_AREA
        )
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


# ---- drawing helpers ------------------------------------------------------------------------


def _clause(metric: str, value: Any, comparison: str, threshold: Any) -> str:
    if comparison == "within":
        return f"{metric} {_fmt(value)} within [{_fmt(threshold[0])}, {_fmt(threshold[1])}]"
    if comparison == "contains":
        return f"{metric} {_fmt(value)} contains {_fmt(threshold)}"
    return f"{metric} {_fmt(value)} {comparison} {_fmt(threshold)}"


def _fmt(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, list):
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    return str(value)


def _ascii(text: str) -> str:
    """Hershey fonts draw ASCII only."""
    return (
        text.replace("—", "-")
        .replace("–", "-")
        .replace("’", "'")
        .encode("ascii", "replace")
        .decode()
    )


def _label(
    img: np.ndarray, text: str, origin: tuple[int, int], colour: tuple, scale: float = 0.8
) -> None:
    (tw, th), base = cv2.getTextSize(text, FONT, scale, 2)
    x, y = origin
    cv2.rectangle(img, (x - 4, y - th - 6), (x + tw + 4, y + base + 2), PAPER, -1)
    cv2.putText(img, text, (x, y), FONT, scale, colour, 2, cv2.LINE_AA)


def header_band(lines: list[str], width: int, colour: tuple) -> np.ndarray:
    scales = [1.5, 1.0, 0.9]
    wrapped: list[tuple[str, float, tuple]] = []
    for i, line in enumerate(lines):
        scale = scales[min(i, len(scales) - 1)]
        for part in _wrap(line, width - 48, scale):
            wrapped.append((part, scale, colour if i == 0 else INK))
    heights = [int(40 * s) + 14 for _, s, _ in wrapped]
    header = np.full((sum(heights) + 36, width, 3), PAPER, dtype=np.uint8)
    cv2.rectangle(header, (0, 0), (12, header.shape[0]), colour, -1)
    y = 18
    for (text, scale, ink), h in zip(wrapped, heights, strict=True):
        y += h
        thickness = 3 if scale >= 1.5 else 2
        cv2.putText(header, text, (32, y - 10), FONT, scale, ink, thickness, cv2.LINE_AA)
    return header


def _wrap(text: str, width: int, scale: float) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if cv2.getTextSize(trial, FONT, scale, 2)[0][0] <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def legend_band(width: int, *, quad: bool = True) -> np.ndarray:
    items = (
        *((("document quad", QUAD),) if quad else ()),
        ("text box", TEXT),
        ("blur tile", BLUR),
        ("glare", GLARE),
        ("hint box", HINT),
    )
    placed: list[tuple[str, tuple, int, int]] = []
    x, row = 32, 0
    for name, colour in items:
        item_w = 60 + cv2.getTextSize(name, FONT, 0.8, 2)[0][0]
        if x + item_w > width - 16 and x > 32:
            x, row = 32, row + 1
        placed.append((name, colour, x, row))
        x += item_w
    strip = np.full((20 + 44 * (row + 1), width, 3), PAPER, dtype=np.uint8)
    for name, colour, x, r in placed:
        y = 20 + 44 * r
        cv2.rectangle(strip, (x, y), (x + 28, y + 24), colour, -1)
        cv2.putText(strip, name, (x + 38, y + 20), FONT, 0.8, INK, 2, cv2.LINE_AA)
    return strip
