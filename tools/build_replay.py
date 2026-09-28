#!/usr/bin/env python3
"""Build the static replay site: a recorded run of the agent loop, rendered as HTML.

Every scene runs the committed synthetic images through the real ``AgentLoop`` /
``process_capture`` / ``invoke()`` path at build time, then writes what came back — the
verdict, the clause that fired, the trace with its ``caused_by`` links, the reviewer's
entries, and the evidence overlay drawn by ``secondlook.overlay``. Nothing runs in the
visitor's browser: the page is a replay of that run, and says so.

    .venv/bin/python tools/build_replay.py <out-dir>     # writes index.html, run.json, img/

``build-pages.sh`` at the repository root calls this to produce the GitHub Pages site.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ENTRY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENTRY / "src"))

from secondlook import overlay  # noqa: E402
from secondlook.agent_loop import (  # noqa: E402
    AGENT_TOOLS,
    AgentLoop,
    Capture,
    StateError,
    capture_view,
    invoke,
    process_capture,
)

DATA = ENTRY / "data" / "synthetic"
REPO_URL = "https://github.com/guptachetan1995/opencv"


@dataclass
class Scene:
    slug: str
    title: str
    lede: str
    capture: dict[str, Any]
    image: str
    trace: list[dict[str, Any]]
    notes: list[str] = field(default_factory=list)


def _successor(cap: Capture) -> str:
    return next(e for e in reversed(cap.trace) if e.action == "request_recapture").outputs[
        "successor_id"
    ]


def _refusal(call) -> str:
    try:
        call()
    except (StateError, RuntimeError, PermissionError) as exc:
        return f"{type(exc).__name__}: {exc}"
    raise AssertionError("expected the call to be refused")


def record_run(img_dir: Path) -> list[Scene]:
    """Run every scene and save its overlay. Returns the scenes in page order."""
    scenes: list[Scene] = []

    def shoot(slug: str, cap: Capture, image_file: str) -> str:
        name = f"{slug}.jpg"
        (img_dir / name).write_bytes(
            overlay.render_jpeg(DATA / image_file, cap.measurements, cap.verdict, max_width=1400)
        )
        return f"img/{name}"

    # 1-3: the retake chain — glare, then a retake that fires a different rule, then clean.
    chain = AgentLoop()
    first = process_capture(chain.open_capture(DATA / "glare_text.jpg"), loop=chain)
    scenes.append(
        Scene(
            "glare",
            "1. Glare across the total: retake",
            "glare_text.jpg is measured. "
            f"{first.measurements.glare_over_text_frac:.0%} of the glare falls on the text "
            "lines, around the total — over the 0.15 threshold — so the cascade says retake, "
            "naming the one metric that failed and a hint box over where it failed.",
            capture_view(first),
            shoot("glare", first, "glare_text.jpg"),
            chain.trace_chain(first.capture_id),
        )
    )
    second_id = _successor(first)
    chain.attach_image(second_id, DATA / "crop_bottom.jpg")
    second = process_capture(second_id, loop=chain)
    scenes.append(
        Scene(
            "retake",
            "2. The retake: glare fixed, a different rule fires",
            "crop_bottom.jpg arrives in the slot the retake request opened. compare_captures "
            "reports the glare fixed, but the new framing cut the bottom of the receipt with "
            "text at the cut, so a different rule fires on a different metric. Nothing "
            "scheduled this second instruction; the second image's measurements chose it.",
            capture_view(second),
            shoot("retake", second, "crop_bottom.jpg"),
            chain.trace_chain(second_id),
        )
    )
    third_id = _successor(second)
    chain.attach_image(third_id, DATA / "clean_a.jpg")
    third = process_capture(third_id, loop=chain)
    scenes.append(
        Scene(
            "accept",
            "3. The second retake: accepted",
            "clean_a.jpg arrives as attempt 3. Every metric is comfortably inside its band, "
            "so the agent accepts it. Accepting is the only thing the agent may finish on "
            "its own.",
            capture_view(third),
            shoot("accept", third, "clean_a.jpg"),
            chain.trace_chain(third_id),
        )
    )

    # 4: not a document — escalated, the agent tools refuse it, a person rejects it.
    batch = AgentLoop()
    escalated = process_capture(batch.open_capture(DATA / "not_doc.jpg"), loop=batch)
    view_before = capture_view(escalated)
    image = shoot("escalate", escalated, "not_doc.jpg")
    refusals = [
        _refusal(
            lambda tool=tool: invoke(
                tool,
                {"previous_id": escalated.capture_id, "new_id": escalated.capture_id}
                if tool == "compare_captures"
                else {"capture_id": escalated.capture_id, "reason": "x"}
                if tool == "escalate"
                else {"capture_id": escalated.capture_id},
                "agent",
                loop=batch,
            )
        )
        for tool in AGENT_TOOLS
    ]
    refusals.append(
        _refusal(
            lambda: invoke("approve", {"capture_id": escalated.capture_id}, "agent", loop=batch)
        )
    )
    invoke(
        "reject",
        {"capture_id": escalated.capture_id, "note": "checked by hand, not a receipt"},
        "reviewer",
        loop=batch,
    )
    scenes.append(
        Scene(
            "escalate",
            "4. Not a receipt: escalated, and only a person moves it",
            "not_doc.jpg has no document quad, so the agent does not guess: it escalates. "
            "While it waits, every agent tool refuses it — the calls below were made against "
            "it and these are their real refusals. Then a reviewer rejects it, and the trace "
            "records the reviewer as the actor.",
            view_before,
            image,
            batch.trace_chain(escalated.capture_id),
            notes=refusals,
        )
    )

    # 5: a suspected duplicate — approve refuses until the reviewer resolves it.
    process_capture(batch.open_capture(DATA / "clean_a.jpg"), loop=batch)
    dup = process_capture(batch.open_capture(DATA / "dup_a.jpg"), loop=batch)
    dup_view = capture_view(dup)
    dup_image = shoot("duplicate", dup, "dup_a.jpg")
    refused_approve = _refusal(
        lambda: invoke("approve", {"capture_id": dup.capture_id}, "reviewer", loop=batch)
    )
    invoke(
        "resolve_duplicate",
        {"capture_id": dup.capture_id, "is_duplicate": True, "note": "same receipt, re-shot"},
        "reviewer",
        loop=batch,
    )
    scenes.append(
        Scene(
            "duplicate",
            "5. A suspected duplicate: a person decides",
            "dup_a.jpg is receipt A re-shot at a different pose. Its perceptual hash lands "
            f"{dup.measurements.nearest_distance} bits from the accepted clean_a.jpg (the "
            "threshold is 6), so the agent escalates it; it can never "
            "auto-reject or auto-accept a duplicate. Even the reviewer's approve is refused "
            "until they say whether it is a duplicate. Here they confirm it is, and it is "
            "rejected.",
            dup_view,
            dup_image,
            batch.trace_chain(dup.capture_id),
            notes=[f"approve before resolving: {refused_approve}"],
        )
    )
    return scenes


# ---- rendering ------------------------------------------------------------------------------


def _e(value: Any) -> str:
    return html.escape(str(value))


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(", ", ": "))


def _verdict_block(view: dict[str, Any]) -> str:
    verdict = view["verdict"]
    fired = [f for f in verdict["firings"] if f["rule_id"] == verdict["rule_id"] and f["matched"]]
    rows = "".join(
        f"<tr><td>{_e(f['metric'])}</td><td>{_e(_compact(f['value']))}</td>"
        f"<td>{_e(f['comparison'])}</td><td>{_e(_compact(f['threshold']))}</td></tr>"
        for f in fired
    )
    table = (
        "<table><caption>The clause that fired</caption><tr><th>metric</th><th>value</th>"
        f"<th>test</th><th>threshold</th></tr>{rows}</table>"
        if rows
        else "<p class='muted'>No rule above <code>accept</code> matched.</p>"
    )
    hint = (
        f"<p><b>Hint box</b> (page pixels, x y w h): <code>{_e(verdict['hint_box'])}</code></p>"
        if verdict["hint_box"]
        else ""
    )
    return (
        f"<p class='verdict {verdict['outcome']}'>{_e(verdict['outcome'].upper())} "
        f"<code>{_e(verdict['rule_id'])}</code></p>"
        f"<p class='instruction'>&ldquo;{_e(verdict['reason_text'])}&rdquo;</p>"
        f"{table}{hint}"
        f"<p class='muted'>capture <code>{_e(view['capture_id'])}</code>, attempt "
        f"{view['attempt']}, state after the agent: <code>{_e(view['state'])}</code></p>"
    )


def _trace_block(trace: list[dict[str, Any]]) -> str:
    rows = "".join(
        f"<tr class='{_e(r['actor'])}'><td>{r['seq']}</td><td>{_e(r['actor'])}</td>"
        f"<td>{_e(r['action'])}</td><td>{_e(_compact(r['inputs']))}</td>"
        f"<td>{_e(_compact(r['outputs']))}</td><td>{_e(r['caused_by'] or '')}</td></tr>"
        for r in trace
    )
    return (
        "<div class='scroll'><table class='trace'><caption>The stored trace</caption>"
        "<tr><th>seq</th><th>actor</th><th>action</th><th>inputs</th><th>outputs</th>"
        f"<th>caused_by</th></tr>{rows}</table></div>"
    )


def render_html(scenes: list[Scene], built_at: str, opencv_version: str) -> str:
    sections = []
    for s in scenes:
        notes = (
            "<ul class='notes'>"
            + "".join(f"<li><code>{_e(n)}</code></li>" for n in s.notes)
            + "</ul>"
            if s.notes
            else ""
        )
        sections.append(
            f"<section class='scene' id='{s.slug}'>"
            f"<figure><img src='{s.image}' alt='Evidence overlay for {_e(s.title)}: the photo as "
            f"posted and the page the measurements read, with the regions they found' />"
            f"</figure><div class='detail'><h2>{_e(s.title)}</h2><p>{_e(s.lede)}</p>"
            f"{_verdict_block(s.capture)}{notes}{_trace_block(s.trace)}</div></section>"
        )
    toc = "".join(f"<li><a href='#{s.slug}'>{_e(s.title)}</a></li>" for s in scenes)
    return PAGE.format(
        built_at=_e(built_at),
        opencv=_e(opencv_version),
        repo=REPO_URL,
        toc=toc,
        sections="".join(sections),
    )


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Second Look — recorded run</title>
<meta name="description" content="A replay of a recorded run of Second Look, an OpenCV 5
receipt-capture inspection agent: each verdict, the clause that fired, the evidence overlay
and the stored trace." />
<style>
  :root {{ color-scheme: light dark; --bg: #ffffff; --fg: #1a1a1a; --muted: #5a5a5a;
          --line: #d6d6d6; --panel: #f6f6f6; --accept: #1e6b35; --retake: #a65400;
          --escalate: #b3261e; --reviewer: #e8f0fe; --link: #1f5fbf; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #15171a; --fg: #e8e8e8; --muted: #a8a8a8; --line: #3a3d42; --panel: #1d2024;
            --accept: #7fcf98; --retake: #f0a35e; --escalate: #f2877e; --reviewer: #22324a;
            --link: #8ab4f8; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--fg); font-family: system-ui, sans-serif;
         line-height: 1.45; }}
  a {{ color: var(--link); }}
  header, footer {{ max-width: 1500px; margin: 0 auto; padding: 1.25rem 16px; }}
  header h1 {{ margin: 0 0 .4rem; font-size: 1.6rem; }}
  .banner {{ border: 1px solid var(--line); background: var(--panel); border-radius: 8px;
            padding: .75rem 1rem; }}
  .muted {{ color: var(--muted); }}
  .scene {{ max-width: 1500px; margin: 0 auto; padding: 1.5rem 16px;
           border-top: 1px solid var(--line); display: grid; gap: 1.5rem; }}
  @media (min-width: 1100px) {{
    .scene {{ grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); min-height: 100vh;
             align-items: start; }}
    .scene figure {{ position: sticky; top: 1rem; }}
  }}
  .scene > * {{ min-width: 0; }}
  figure {{ margin: 0; }}
  img {{ display: block; max-width: 100%; height: auto; max-height: calc(100vh - 2rem);
        border: 1px solid var(--line); }}
  h2 {{ margin: 0 0 .5rem; font-size: 1.3rem; }}
  .verdict {{ font-weight: 700; font-size: 1.15rem; margin: .75rem 0 .25rem; }}
  .verdict.accept {{ color: var(--accept); }} .verdict.retake {{ color: var(--retake); }}
  .verdict.escalate {{ color: var(--escalate); }}
  .instruction {{ font-style: italic; margin-top: 0; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .85rem; margin: .5rem 0 1rem; }}
  caption {{ text-align: left; font-weight: 600; padding-bottom: .25rem; }}
  th, td {{ border-bottom: 1px solid var(--line); padding: .25rem .35rem; text-align: left;
           vertical-align: top; }}
  td {{ font-family: ui-monospace, monospace; word-break: break-word; }}
  tr.reviewer td {{ background: var(--reviewer); font-weight: 600; }}
  .trace td {{ font-size: .8rem; }}
  .trace td:nth-child(-n+3), .trace td:last-child {{ white-space: nowrap; word-break: normal; }}
  .scroll {{ overflow-x: auto; }}
  .notes {{ padding-left: 1.1rem; font-size: .85rem; }}
  .notes code {{ word-break: break-word; }}
  nav ol {{ margin: .5rem 0 0; }}
</style>
</head>
<body>
<header>
  <h1>Second Look — a recorded run</h1>
  <p class="banner"><b>This page is a replay, not a live service.</b> It was built on
  {built_at} by <code>tools/build_replay.py</code>, which ran the committed synthetic receipt
  images through the real agent loop (OpenCV {opencv}) and wrote down what came back: every
  verdict, the clause that fired, the evidence overlay OpenCV drew, and the stored trace with
  its <code>caused_by</code> links. Nothing runs in your browser. To run it yourself, clone
  <a href="{repo}">{repo}</a> and follow its README.</p>
  <nav><b>Scenes</b><ol>{toc}</ol></nav>
</header>
{sections}
<footer class="muted">MIT licensed. The images are synthetic and generated from a fixed seed;
no real receipt or photograph appears here. Source: <a href="{repo}">{repo}</a>.</footer>
</body>
</html>
"""


def build(out_dir: Path) -> list[Scene]:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"build_replay: {out_dir} is not empty; pass a new or empty directory")
    img_dir = out_dir / "img"
    img_dir.mkdir(parents=True)
    scenes = record_run(img_dir)
    built_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    opencv_version = scenes[0].capture["measurements"]["opencv_version"]
    (out_dir / "index.html").write_text(render_html(scenes, built_at, opencv_version))
    run = {
        "built_at": built_at,
        "opencv_version": opencv_version,
        "scenes": [
            {
                "slug": s.slug,
                "title": s.title,
                "capture": s.capture,
                "trace": s.trace,
                "notes": s.notes,
                "image": s.image,
            }
            for s in scenes
        ],
    }
    (out_dir / "run.json").write_text(json.dumps(run, indent=1))
    return scenes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path, help="directory to write the site into")
    args = parser.parse_args(argv)
    scenes = build(args.out_dir.resolve())
    print(f"wrote {len(scenes)} scenes to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
