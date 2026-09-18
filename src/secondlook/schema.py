"""The structured records the pipeline emits (SPEC § 6).

Every field of ``Measurements`` is a number, a bool, a short enum string, a list of boxes or
a list of points. No pixel data and no decoded text is ever stored: a QR's payload is
dropped inside the metric that read it, and only ``code_decoded`` survives.

Coordinate spaces: ``quad`` is the one frame-space region (pixels of the posted image).
Every other box is in rectified-page pixels, whose extent is ``page_shape``. The overlay
goal maps page boxes back onto the frame with the homography it rebuilds from ``quad`` and
``page_shape``; nothing here needs the matrix.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Box = list[int]  # [x, y, w, h]
Point = list[int]  # [x, y]

Outcome = Literal["accept", "retake", "escalate"]

# The issue's three words, mapped onto the SPEC's field names. test_schema.py asserts each
# group's type contract; policy.py reads none of these, it reads fields by name.
REGION_FIELDS: tuple[str, ...] = ("quad", "blur_tiles", "glare_boxes", "text_boxes")
FLAG_FIELDS: tuple[str, ...] = (
    "quad_found",
    "bottom_band_has_text",
    "code_decoded",
    "edge_touch_sides",
)
CONFIDENCE_FIELDS: tuple[str, ...] = (
    "corner_confidence",
    "page_area_fraction",
    "second_quad_area_fraction",
    "clipped_low_frac",
    "clipped_high_frac",
    "glare_area_fraction",
    "glare_over_text_frac",
    "text_coverage_fraction",
)


@dataclass(frozen=True)
class Measurements:
    """One record per ``inspect`` call. Field order follows SPEC § 4's measurement order."""

    image_shape: list[int]
    page_shape: list[int]
    # 1 — document localisation and rectification
    quad_found: bool
    quad: list[Point] | None
    page_area_fraction: float
    corner_confidence: float
    second_quad_area_fraction: float
    # 2 — focus, per tile
    focus_global: float
    focus_min_tile: float
    blur_tiles: list[Box]
    # 3 — exposure and contrast
    clipped_low_frac: float
    clipped_high_frac: float
    contrast_p95_p5: float
    # 4 — specular glare
    glare_area_fraction: float
    glare_boxes: list[Box]
    glare_over_text_frac: float
    # 5 — text presence and coverage
    text_box_count: int
    text_coverage_fraction: float
    text_median_height_px: float
    bottom_band_has_text: bool
    text_boxes: list[Box]
    # 6 — frame-edge crop
    edge_touch_sides: list[str]
    # 7 — machine-readable code
    code_kind: str | None
    code_decoded: bool
    # 8 — duplicate
    phash: str
    nearest_distance: int
    duplicate_of: str | None
    # provenance
    opencv_version: str
    dnn_engine: str
    text_detector: str
    elapsed_ms: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Measurements:
        return cls(**data)


@dataclass(frozen=True)
class RuleFiring:
    """One evaluated clause. ``threshold`` is a two-element list for a ``within`` check."""

    rule_id: str
    matched: bool
    metric: str
    value: Any
    threshold: Any
    comparison: str


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    rule_id: str
    reason_code: str
    reason_text: str
    hint_box: Box | None
    firings: list[RuleFiring] = field(default_factory=list)
    decided_by: Literal["policy", "reviewer"] = "policy"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Verdict:
        firings = [RuleFiring(**f) for f in data.get("firings", [])]
        return cls(**{**data, "firings": firings})


Actor = Literal["agent", "reviewer"]  # `actor` is the field the human gate is auditable through


@dataclass(frozen=True)
class TraceEntry:
    """One append-only row of a capture's trace. ``caused_by`` is the ``seq`` of the entry
    whose output chose this action — the field that turns the trace from a log into
    evidence that a measurement chose the next call (SPEC § 6)."""

    seq: int
    at: str
    actor: Actor
    action: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    caused_by: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceEntry:
        return cls(**data)
