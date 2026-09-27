#!/usr/bin/env python3
"""Render the synthetic receipt set (the primary sample set) from a fixed seed.

Pillow draws three receipt papers; OpenCV applies every defect with known parameters and
warps each paper onto a textured table frame at ground-truth corners; the result is saved
as JPEG q85 at 1200×1600 — the size and quality the phone client is meant to post. Because
the defect is applied here, ``manifest.json`` carries exact ground truth for every sample:
which defect, where, how much, and the verdict the policy is expected to reach.

    python tools/make_samples.py --out data/synthetic [--seed 20260908]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFont

SEED = 20260908
FRAME_W, FRAME_H = 1200, 1600
PAPER_W = 520
PAPER_RGB = (232, 233, 229)
INK_RGB = (28, 30, 34)
TABLE_BGR = (74, 90, 108)
JPEG_QUALITY = 85

Corners = list[tuple[float, float]]  # TL, TR, BR, BL in frame pixels

RECEIPTS: dict[str, dict[str, Any]] = {
    "a": {
        "shop": "HARBOUR HARDWARE",
        "address": [
            "12 Quay Street, Tilbury RM18",
            "Tel 01375 555 0142",
            "VAT No. GB 442 9911 07",
        ],
        "date": "14/08/2026  11:42   Till 3   Op. SK",
        "items": [
            ("Cable ties 200mm x100", "4.99"),
            ("Duct tape 50m silver", "6.49"),
            ("Marker pen black x2", "2.80"),
            ("Ranging pole 2m", "18.50"),
            ("Chalk line refill", "3.25"),
            ("Work gloves L", "7.99"),
            ("Spray paint orange", "5.60"),
            ("Tape measure 8m", "11.99"),
            ("Batteries AA x8", "6.75"),
            ("Padlock 40mm", "9.49"),
            ("Bin bags heavy x20", "4.20"),
        ],
        "payment": ["VISA DEBIT  ****4471", "AUTH 083112   CONTACTLESS"],
        "footer": ["Thank you for shopping with us", "Keep this receipt for returns"],
        "tail": 210,
    },
    "b": {
        "shop": "THE KESTREL CAFE",
        "logo": True,
        "address": ["Unit 4, Marsh Lane Retail Park", "Grays RM20 3XT", "www.kestrelcafe.example"],
        "date": "14/08/2026  13:05   Table 6",
        "items": [
            ("Soup of the day", "5.50"),
            ("Chicken club sandwich", "8.95"),
            ("Jacket potato tuna", "7.25"),
            ("Flat white", "3.10"),
            ("Flat white", "3.10"),
            ("Sparkling water 500ml", "2.40"),
            ("Carrot cake slice", "3.95"),
        ],
        "payment": ["MASTERCARD  ****0219", "AUTH 91A44Z   CHIP & PIN", "Service not included"],
        "footer": ["Thanks for visiting!", "Wifi: kestrel-guest"],
        "tail": 230,
    },
    "c": {
        "shop": "PARKRIGHT TILBURY DOCKS",
        "address": [
            "Car Park B, Ferry Road",
            "Operated by Parkright Ltd",
            "VAT No. GB 118 0442 39",
        ],
        "date": "15/08/2026  07:58   Bay 112",
        "items": [
            ("Parking 07:58 - 18:00", "12.00"),
            ("Extended stay surcharge", "2.50"),
        ],
        "payment": ["VISA  ****4471", "AUTH 224901   CONTACTLESS"],
        "footer": [
            "Fiscal QR below - keep for your records",
            "Display this receipt on the dashboard",
        ],
        "qr": "PRT-2026-08-15-0758-B112-000014.50",
        "tail": 200,
    },
}


# ---- rendering -----------------------------------------------------------------------------


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _blend(alpha: float) -> tuple[int, int, int]:
    return tuple(
        int(round(p * (1 - alpha) + i * alpha)) for p, i in zip(PAPER_RGB, INK_RGB, strict=True)
    )


def render_qr(text: str, module_px: int = 9) -> np.ndarray:
    encoder = cv2.QRCodeEncoder.create()
    code = encoder.encode(text)
    code = cv2.resize(code, None, fx=module_px, fy=module_px, interpolation=cv2.INTER_NEAREST)
    quiet = 4 * module_px
    return cv2.copyMakeBorder(code, quiet, quiet, quiet, quiet, cv2.BORDER_CONSTANT, value=255)


def render_paper(
    key: str, rng: np.random.Generator, *, ink_alpha: float = 1.0
) -> tuple[np.ndarray, dict]:
    """Draw a receipt with Pillow's bundled font. Returns (BGR paper, layout in paper px)."""
    spec = RECEIPTS[key]
    ink = _blend(ink_alpha)
    canvas = Image.new("RGB", (PAPER_W, 2400), PAPER_RGB)
    draw = ImageDraw.Draw(canvas)
    big, body, small, total_font = _font(30), _font(22), _font(19), _font(27)
    left, right = 28, PAPER_W - 28
    y = 44

    def centred(text: str, fnt: ImageFont.FreeTypeFont, dy: int) -> None:
        nonlocal y
        w = draw.textlength(text, font=fnt)
        draw.text(((PAPER_W - w) / 2, y), text, font=fnt, fill=ink)
        y += dy

    def row(
        name: str, price: str, fnt: ImageFont.FreeTypeFont, dy: int, bold: bool = False
    ) -> None:
        nonlocal y
        draw.text((left, y), name, font=fnt, fill=ink)
        w = draw.textlength(price, font=fnt)
        draw.text((right - w, y), price, font=fnt, fill=ink)
        if bold:
            draw.text((left + 1, y), name, font=fnt, fill=ink)
            draw.text((right - w + 1, y), price, font=fnt, fill=ink)
        y += dy

    def rule() -> None:
        nonlocal y
        draw.text((left, y), "-" * 38, font=small, fill=ink)
        y += 30

    if spec.get("logo"):
        draw.rectangle((left, y, right, y + 64), fill=ink)
        w = draw.textlength(spec["shop"], font=big)
        draw.text(((PAPER_W - w) / 2, y + 14), spec["shop"], font=big, fill=PAPER_RGB)
        y += 84
    else:
        centred(spec["shop"], big, 42)
    for line in spec["address"]:
        centred(line, small, 26)
    y += 12
    draw.text((left, y), spec["date"], font=small, fill=ink)
    y += 34
    rule()
    for name, price in spec["items"]:
        row(name, price, body, 32)
    rule()
    subtotal = sum(float(p) for _, p in spec["items"])
    tax = round(subtotal / 6, 2)
    row("Subtotal", f"{subtotal:.2f}", body, 32)
    row("VAT 20%", f"{tax:.2f}", body, 36)
    total_y = y + 14
    row("TOTAL", f"{subtotal + tax:.2f}", total_font, 44, bold=True)
    rule()
    for line in spec["payment"]:
        draw.text((left, y), line, font=small, fill=ink)
        y += 27
    y += 16
    for line in spec["footer"]:
        centred(line, small, 27)
    layout: dict[str, Any] = {"total_y": total_y}
    if spec.get("qr"):
        y += 16
        qr = render_qr(spec["qr"])
        qr_rgb = np.where(
            qr[..., None] > 127, np.array(PAPER_RGB, np.uint8), np.array(INK_RGB, np.uint8)
        )
        qr_img = Image.fromarray(qr_rgb.astype(np.uint8), "RGB")
        x = (PAPER_W - qr.shape[1]) // 2
        canvas.paste(qr_img, (x, y))
        layout["qr_box"] = [x, y, qr.shape[1], qr.shape[0]]
        y += qr.shape[0] + 12
    layout["tail_y0"] = y + 10
    height = y + spec["tail"]
    layout["height"] = height

    paper = np.asarray(canvas.crop((0, 0, PAPER_W, height)), dtype=np.float32)
    gradient = np.linspace(-3, 3, height, dtype=np.float32)[:, None, None]
    paper = paper + gradient + rng.normal(0.0, 1.6, paper.shape).astype(np.float32)
    bgr = np.clip(paper, 0, 255).astype(np.uint8)[:, :, ::-1]
    return np.ascontiguousarray(bgr), layout


# ---- paper-space defects -------------------------------------------------------------------


def blur_from(paper: np.ndarray, y0: int, sigma: float) -> np.ndarray:
    out = paper.copy()
    out[y0:] = cv2.GaussianBlur(paper[y0:], (0, 0), sigma)
    return out


def glare_ellipse(paper: np.ndarray, centre: tuple[int, int], axes: tuple[int, int]) -> np.ndarray:
    """A saturated specular ellipse (the ground-truth area) with a dimmer halo around it that
    stays under the detector's value floor."""
    out = paper.astype(np.float32)
    halo = np.zeros(paper.shape[:2], np.float32)
    cv2.ellipse(halo, centre, (int(axes[0] * 1.35), int(axes[1] * 1.35)), 0, 0, 360, 1.0, -1)
    halo = cv2.GaussianBlur(halo, (0, 0), 6)
    out = out + halo[..., None] * 12.0
    core = np.zeros(paper.shape[:2], np.float32)
    cv2.ellipse(core, centre, axes, 0, 0, 360, 1.0, -1)
    out = out * (1 - core[..., None]) + 255.0 * core[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


# ---- the frame -----------------------------------------------------------------------------


def make_table(rng: np.random.Generator) -> np.ndarray:
    ys, xs = np.mgrid[0:FRAME_H, 0:FRAME_W].astype(np.float32)
    grain = (
        6 * np.sin(xs / 37.0 + ys / 211.0)
        + 5 * np.sin(ys / 53.0 - xs / 149.0)
        + 3 * np.sin((xs + ys) / 17.0)
    )
    cx, cy = FRAME_W / 2, FRAME_H / 2
    vignette = 1.0 - 0.18 * (((xs - cx) / cx) ** 2 + ((ys - cy) / cy) ** 2)
    table = np.empty((FRAME_H, FRAME_W, 3), np.float32)
    for ch, base in enumerate(TABLE_BGR):
        table[..., ch] = (base + grain) * vignette
    table += rng.normal(0.0, 2.5, table.shape).astype(np.float32)
    return np.clip(table, 0, 255).astype(np.uint8)


def pose_corners(
    paper_shape: tuple[int, int],
    *,
    centre: tuple[float, float],
    scale: float,
    angle_deg: float,
    skew: float = 0.0,
) -> Corners:
    """Corners of a paper of ``paper_shape`` placed on the table: scaled, rotated about its
    centre, with the top edge narrowed by ``skew`` (a camera tilted toward the viewer)."""
    h, w = paper_shape
    hw, hh = w * scale / 2, h * scale / 2
    rect = np.array(
        [
            [-hw * (1 - skew), -hh],
            [hw * (1 - skew), -hh],
            [hw * (1 + skew), hh],
            [-hw * (1 + skew), hh],
        ],
        np.float32,
    )
    t = math.radians(angle_deg)
    rot = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]], np.float32)
    pts = rect @ rot.T + np.array(centre, np.float32)
    return [(float(x), float(y)) for x, y in pts]


def compose(frame: np.ndarray, paper: np.ndarray, corners: Corners) -> np.ndarray:
    h, w = paper.shape[:2]
    src = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
    dst = np.array(corners, np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(paper, matrix, (FRAME_W, FRAME_H), flags=cv2.INTER_LINEAR)
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), matrix, (FRAME_W, FRAME_H))
    shadow = (
        cv2.GaussianBlur(np.roll(mask, (14, 9), axis=(0, 1)), (0, 0), 12).astype(np.float32) / 255
    )
    out = frame.astype(np.float32) * (1 - 0.35 * shadow[..., None])
    soft = cv2.GaussianBlur(mask, (0, 0), 0.7).astype(np.float32)[..., None] / 255
    out = out * (1 - soft) + warped.astype(np.float32) * soft
    return np.clip(out, 0, 255).astype(np.uint8)


def finish(
    frame: np.ndarray, rng: np.random.Generator, *, sigma: float = 0.0, gain: float = 1.0
) -> np.ndarray:
    out = frame.astype(np.float32)
    if sigma > 0:
        out = cv2.GaussianBlur(out, (0, 0), sigma)
    out = out * gain + rng.normal(0.0, 2.0, out.shape).astype(np.float32)
    return np.clip(out, 0, 255).astype(np.uint8)


# ---- the set -------------------------------------------------------------------------------


def build(out_dir: Path, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    paper_a, lay_a = render_paper("a", rng)
    paper_b, lay_b = render_paper("b", rng)
    paper_c, lay_c = render_paper("c", rng)
    paper_faded, _ = render_paper("a", rng, ink_alpha=0.08)
    pose_a = pose_corners(
        paper_a.shape[:2], centre=(602, 802), scale=1.0, angle_deg=1.2, skew=0.02
    )
    pose_b = pose_corners(
        paper_b.shape[:2], centre=(598, 790), scale=1.0, angle_deg=-1.5, skew=0.03
    )
    pose_c = pose_corners(
        paper_c.shape[:2], centre=(604, 796), scale=1.0, angle_deg=0.8, skew=0.02
    )
    samples: list[dict[str, Any]] = []

    def emit(
        sample_id: str,
        frame: np.ndarray,
        *,
        base: str | None,
        defect: str,
        params: dict[str, Any],
        corners: Corners | None,
        paper_shape: tuple[int, int] | None,
        expected: tuple[str, str] | None,
        note: str,
    ) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        assert ok
        (out_dir / f"{sample_id}.jpg").write_bytes(buf.tobytes())
        samples.append(
            {
                "id": sample_id,
                "file": f"{sample_id}.jpg",
                "base": base,
                "defect": defect,
                "params": params,
                "corners": [[round(x, 1), round(y, 1)] for x, y in corners] if corners else None,
                "paper_size": [paper_shape[1], paper_shape[0]] if paper_shape else None,
                "expected_verdict": {"outcome": expected[0], "rule_id": expected[1]}
                if expected
                else None,
                "note": note,
            }
        )

    def shot(
        paper: np.ndarray, corners: Corners, *, sigma: float = 0.0, gain: float = 1.0
    ) -> np.ndarray:
        return finish(compose(make_table(rng), paper, corners), rng, sigma=sigma, gain=gain)

    a_shape, b_shape, c_shape = paper_a.shape[:2], paper_b.shape[:2], paper_c.shape[:2]

    emit(
        "clean_a",
        shot(paper_a, pose_a),
        base="a",
        defect="none",
        params={},
        corners=pose_a,
        paper_shape=a_shape,
        expected=("accept", "accept"),
        note="reference capture of receipt A",
    )
    emit(
        "clean_b",
        shot(paper_b, pose_b),
        base="b",
        defect="none",
        params={},
        corners=pose_b,
        paper_shape=b_shape,
        expected=("accept", "accept"),
        note="reference capture of receipt B",
    )

    for sigma, expected in ((1.0, None), (2.0, None), (4.0, ("retake", "out_of_focus"))):
        emit(
            f"blur_{int(sigma)}",
            shot(paper_a, pose_a, sigma=sigma),
            base="a",
            defect="blur_global",
            params={"space": "frame", "sigma": sigma},
            corners=pose_a,
            paper_shape=a_shape,
            expected=expected,
            note="whole frame blurred; focus must fall monotonically with sigma",
        )

    y0 = int(0.6 * a_shape[0])
    emit(
        "blur_bottom",
        shot(blur_from(paper_a, y0, 4.0), pose_a),
        base="a",
        defect="blur_partial",
        params={"space": "paper", "sigma": 4.0, "from_fraction": 0.6, "from_y": y0},
        corners=pose_a,
        paper_shape=a_shape,
        expected=("retake", "out_of_focus"),
        note="bottom 40% of the paper blurred; blur_tiles must sit in that band only",
    )

    centre = (PAPER_W // 2 + 20, lay_a["total_y"] + 10)
    axes = (150, 46)
    area = math.pi * axes[0] * axes[1] / (a_shape[0] * a_shape[1])
    emit(
        "glare_text",
        shot(glare_ellipse(paper_a, centre, axes), pose_a),
        base="a",
        defect="glare",
        params={
            "space": "paper",
            "centre": list(centre),
            "axes": list(axes),
            "area_fraction": round(area, 5),
            "over_text": True,
        },
        corners=pose_a,
        paper_shape=a_shape,
        expected=("retake", "glare_over_total"),
        note="specular ellipse across the TOTAL line",
    )

    centre = (PAPER_W // 2 - 10, lay_a["tail_y0"] + 95)
    axes = (120, 40)
    area = math.pi * axes[0] * axes[1] / (a_shape[0] * a_shape[1])
    emit(
        "glare_white",
        shot(glare_ellipse(paper_a, centre, axes), pose_a),
        base="a",
        defect="glare",
        params={
            "space": "paper",
            "centre": list(centre),
            "axes": list(axes),
            "area_fraction": round(area, 5),
            "over_text": False,
        },
        corners=pose_a,
        paper_shape=a_shape,
        expected=("accept", "accept"),
        note="specular ellipse on the blank tail; must not trigger a retake",
    )

    warp = [(250.0, 200.0), (900.0, 140.0), (980.0, 1500.0), (180.0, 1420.0)]
    emit(
        "warp",
        shot(paper_b, warp),
        base="b",
        defect="perspective",
        params={"space": "frame"},
        corners=warp,
        paper_shape=b_shape,
        expected=("accept", "accept"),
        note="strong keystone; the detected quad must land on these corners",
    )

    visible = lay_a["total_y"] - 40
    top = FRAME_H - visible
    crop = pose_corners(
        a_shape, centre=(600, top + a_shape[0] / 2), scale=1.0, angle_deg=0.6, skew=0.015
    )
    emit(
        "crop_bottom",
        shot(paper_a, crop),
        base="a",
        defect="crop",
        params={"space": "frame", "side": "bottom", "visible_paper_height": visible},
        corners=crop,
        paper_shape=a_shape,
        expected=("retake", "bottom_edge_clipped"),
        note="receipt runs off the bottom of the frame just above the TOTAL line",
    )

    emit(
        "under",
        shot(paper_a, pose_a, gain=0.12),
        base="a",
        defect="exposure",
        params={"space": "frame", "gain": 0.12},
        corners=pose_a,
        paper_shape=a_shape,
        expected=("retake", "underexposed"),
        note="whole frame at 12% gain",
    )
    emit(
        "over",
        shot(paper_a, pose_a, gain=1.6),
        base="a",
        defect="exposure",
        params={"space": "frame", "gain": 1.6},
        corners=pose_a,
        paper_shape=a_shape,
        expected=("retake", "overexposed"),
        note="whole frame at 160% gain; paper saturates",
    )

    emit(
        "not_doc",
        finish(make_table(rng), rng),
        base=None,
        defect="not_a_document",
        params={},
        corners=None,
        paper_shape=None,
        expected=("escalate", "not_a_document"),
        note="the table with nothing on it",
    )

    emit(
        "faded",
        shot(paper_faded, pose_a),
        base="a",
        defect="faded",
        params={"space": "paper", "ink_alpha": 0.08},
        corners=pose_a,
        paper_shape=a_shape,
        expected=("escalate", "not_a_document"),
        note=(
            "thermal paper faded to 8% ink; the quad is found but text coverage is under the floor"
        ),
    )

    left = pose_corners(a_shape, centre=(318, 800), scale=0.56, angle_deg=2.0, skew=0.02)
    right_ = pose_corners(b_shape, centre=(878, 790), scale=0.56, angle_deg=-3.0, skew=0.02)
    frame = compose(compose(make_table(rng), paper_a, left), paper_b, right_)
    emit(
        "two_docs",
        finish(frame, rng),
        base="a+b",
        defect="two_documents",
        params={
            "space": "frame",
            "second_corners": [[round(x, 1), round(y, 1)] for x, y in right_],
        },
        corners=left,
        paper_shape=a_shape,
        expected=("escalate", "two_documents"),
        note="two receipts side by side; the larger is the primary quad",
    )

    dup = pose_corners(a_shape, centre=(614, 788), scale=0.99, angle_deg=-1.4, skew=0.03)
    emit(
        "dup_a",
        shot(paper_a, dup),
        base="a",
        defect="duplicate",
        params={"space": "frame", "duplicate_of": "clean_a"},
        corners=dup,
        paper_shape=a_shape,
        expected=("escalate", "suspected_duplicate"),
        note=(
            "receipt A re-shot at a different pose; escalates when clean_a's hash is in the batch"
        ),
    )

    emit(
        "qr_soft",
        shot(paper_c, pose_c, sigma=2.2),
        base="c",
        defect="blur_global",
        params={"space": "frame", "sigma": 2.2, "qr_box": lay_c["qr_box"]},
        corners=pose_c,
        paper_shape=c_shape,
        expected=("accept", "accept"),
        note="soft enough to trip focus_min_tile, but the fiscal QR still decodes, so no retake",
    )

    manifest = {
        "generator": "tools/make_samples.py",
        "seed": seed,
        "frame": [FRAME_W, FRAME_H],
        "jpeg_quality": JPEG_QUALITY,
        "opencv": cv2.__version__,
        "pillow": PIL.__version__,
        "layouts": {"a": lay_a, "b": lay_b, "c": lay_c},
        "samples": samples,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    manifest = build(args.out, args.seed)
    print(f"wrote {len(manifest['samples'])} samples to {args.out}")


if __name__ == "__main__":
    main()
