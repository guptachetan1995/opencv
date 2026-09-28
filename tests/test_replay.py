"""The static replay site: built from a real run, and honest that it is a replay."""

from __future__ import annotations

import json
import subprocess
import sys

from conftest import ENTRY
from secondlook.agent_loop import AGENT_TOOLS

sys.path.insert(0, str(ENTRY / "tools"))

from build_replay import build  # noqa: E402


def test_replay_records_every_scene_from_the_real_loop(tmp_path):
    scenes = build(tmp_path / "site")
    assert [s.slug for s in scenes] == ["glare", "retake", "accept", "escalate", "duplicate"]
    rules = [s.capture["verdict"]["rule_id"] for s in scenes]
    assert rules == [
        "glare_over_total",
        "bottom_edge_clipped",
        "accept",
        "not_a_document",
        "suspected_duplicate",
    ]
    escalate = next(s for s in scenes if s.slug == "escalate")
    # One real refusal per agent tool, plus the agent reaching for approve.
    assert len(escalate.notes) == len(AGENT_TOOLS) + 1
    assert all(n.startswith("StateError") for n in escalate.notes[: len(AGENT_TOOLS)])
    assert escalate.notes[-1].startswith("PermissionError")
    assert escalate.trace[-1]["actor"] == "reviewer"

    site = tmp_path / "site"
    html = (site / "index.html").read_text()
    assert "This page is a replay, not a live service." in html
    run = json.loads((site / "run.json").read_text())
    for scene in run["scenes"]:
        assert (site / scene["image"]).read_bytes()[:3] == b"\xff\xd8\xff"


def test_build_pages_refuses_a_non_empty_directory(tmp_path):
    (tmp_path / "keep.txt").write_text("not ours")
    result = subprocess.run(
        [str(ENTRY / "build-pages.sh"), str(tmp_path)], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert (tmp_path / "keep.txt").exists()
