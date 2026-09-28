#!/usr/bin/env python3
"""Draw the README's hero image from a real run of the agent loop.

Three committed images go through the same ``process_capture`` / ``invoke()`` path the demo
and the tests use, and each panel is the evidence overlay (``secondlook.overlay``) of what
came back — nothing is hand-placed:

1. ``glare_text.jpg`` — retake on ``glare_over_total``, the hint box over the glare.
2. ``crop_bottom.jpg``, posted as that capture's retake — the glare is reported fixed by
   ``compare_captures``, and a different rule, ``bottom_edge_clipped``, fires on a
   different metric.
3. ``not_doc.jpg`` — no document found, so the agent escalates to a person.

    .venv/bin/python tools/make_hero.py            # writes docs/hero.jpg
    .venv/bin/python tools/make_hero.py --out x.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ENTRY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENTRY / "src"))

from secondlook import overlay  # noqa: E402
from secondlook.agent_loop import AgentLoop, Capture, process_capture  # noqa: E402

DATA = ENTRY / "data" / "synthetic"
DEFAULT_OUT = ENTRY / "docs" / "hero.jpg"
PANEL_W = 800
GAP = 28


def run_captures() -> list[tuple[str, Capture, list[str]]]:
    """The three captures, each with the extra header lines its trace justifies."""
    loop = AgentLoop()
    first = process_capture(loop.open_capture(DATA / "glare_text.jpg"), loop=loop)
    successor_id = next(e for e in first.trace if e.action == "request_recapture").outputs[
        "successor_id"
    ]
    loop.attach_image(successor_id, DATA / "crop_bottom.jpg")
    second = process_capture(successor_id, loop=loop)
    compare = next(e for e in second.trace if e.action == "compare_captures")
    compare_line = (
        f"compare_captures: {compare.inputs['metric']} {compare.inputs['before']:.2f} -> "
        f"{compare.outputs['after']:.2f}, {compare.outputs['status']}"
    )
    other = AgentLoop()
    third = process_capture(other.open_capture(DATA / "not_doc.jpg"), loop=other)
    return [
        ("1. glare_text.jpg", first, []),
        ("2. crop_bottom.jpg (its retake)", second, [compare_line]),
        ("3. not_doc.jpg", third, []),
    ]


def panel(title: str, cap: Capture, extra: list[str]) -> np.ndarray:
    bgr = cv2.imread(str(cap.image_path))
    page = overlay.annotate_page(bgr, cap.measurements, cap.verdict)
    lines = overlay.headline(cap.verdict)
    header = overlay.header_band(
        [title, *lines[:2], *extra, *lines[2:]], PANEL_W, overlay.OUTCOME[cap.verdict.outcome]
    )
    return np.vstack([header, page])


def compose(panels: list[np.ndarray]) -> np.ndarray:
    height = max(p.shape[0] for p in panels)
    width = sum(p.shape[1] for p in panels) + GAP * (len(panels) + 1)
    canvas = np.full((height + 2 * GAP, width, 3), overlay.PAPER, dtype=np.uint8)
    x = GAP
    for p in panels:
        canvas[GAP : GAP + p.shape[0], x : x + p.shape[1]] = p
        x += p.shape[1] + GAP
    title = overlay.header_band(
        [
            "Second Look: what OpenCV 5 measured, and the next call it chose",
            "Each panel is the page the measurements read (the rectified receipt, or the whole "
            "frame when no document is found), drawn from the stored record of a real run "
            "through the agent loop.",
        ],
        width,
        overlay.INK,
    )
    return np.vstack([title, canvas, overlay.legend_band(width, quad=False)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    image = compose([panel(*row) for row in run_captures()])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(overlay.encode_jpeg(image, max_width=1800, quality=88))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
