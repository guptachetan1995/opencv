"""The evidence overlay: drawn from the real measurements of a committed image, onto the
page the measurements were taken from, and never written anywhere."""

from __future__ import annotations

import cv2
import numpy as np

from conftest import DATA
from secondlook import overlay
from secondlook.agent_loop import AgentLoop, process_capture


def _processed(sample: str):
    loop = AgentLoop()
    cap = process_capture(loop.open_capture(DATA / f"{sample}.jpg"), loop=loop)
    return cv2.imread(str(DATA / f"{sample}.jpg")), cap


def test_rectified_page_matches_the_measured_page_shape():
    bgr, cap = _processed("glare_text")
    page = overlay.rectified_page(bgr, cap.measurements)
    assert list(page.shape[:2]) == cap.measurements.page_shape


def test_hint_box_is_drawn_where_the_verdict_put_it():
    bgr, cap = _processed("glare_text")
    x, y, w, h = cap.verdict.hint_box
    page = overlay.annotate_page(bgr, cap.measurements, cap.verdict)
    # The hint box's left edge, halfway down: the overlay's red (BGR) stroke, not paper.
    b, g, r = (int(v) for v in page[y + h // 2, x + 2])
    assert r > 150 and g < 100 and b < 100


def test_headline_quotes_the_clause_that_fired():
    _, cap = _processed("glare_text")
    lines = overlay.headline(cap.verdict)
    assert lines[0] == "RETAKE  glare_over_total"
    assert lines[1] == "glare_over_text_frac 0.92 > 0.15"
    assert lines[2] == cap.verdict.reason_text


def test_render_handles_a_frame_with_no_document():
    bgr, cap = _processed("not_doc")
    assert cap.measurements.quad is None
    image = overlay.render(bgr, cap.measurements, cap.verdict)
    assert image.ndim == 3 and image.shape[0] > cap.measurements.page_shape[0]
    assert overlay.headline(cap.verdict)[1] == "quad_found False == False"


def test_render_jpeg_returns_bytes_and_leaves_the_record_untouched():
    _, cap = _processed("blur_bottom")
    before = cap.measurements.to_dict()
    data = overlay.render_jpeg(DATA / "blur_bottom.jpg", cap.measurements, cap.verdict)
    assert data[:3] == b"\xff\xd8\xff"
    decoded = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[1] <= 1400
    assert cap.measurements.to_dict() == before


def test_hero_image_is_drawn_from_a_real_run(tmp_path):
    import sys

    from conftest import ENTRY

    sys.path.insert(0, str(ENTRY / "tools"))
    import make_hero

    rows = make_hero.run_captures()
    assert [cap.verdict.rule_id for _, cap, _ in rows] == [
        "glare_over_total",
        "bottom_edge_clipped",
        "not_a_document",
    ]
    assert rows[1][2] == ["compare_captures: glare_over_text_frac 0.92 -> 0.00, fixed"]
    out = tmp_path / "hero.jpg"
    make_hero.main(["--out", str(out)])
    assert out.read_bytes()[:3] == b"\xff\xd8\xff"
