# Second Look

![Three receipt photos as Second Look's evidence overlay draws them: glare over the total gets a retake with a hint box; the retake fixes the glare but clips the bottom edge, so a different rule asks for another retake; a photo with no document is escalated to a person.](./docs/hero.jpg)

*Drawn by [`tools/make_hero.py`](./tools/make_hero.py) from a real run of the agent loop:
each panel is the page OpenCV 5 measured, with the regions it found and the call the
measurement chose next.*

A bad receipt photo is cheap to fix for about two seconds — glare across the total, the
bottom third out of focus, the tax line cropped off the frame — while the person who took it
is still standing there. Three weeks later, when a bookkeeper finally opens the capture, it
isn't fixable at all: the surveyor is on another site and the paper is in a bin, and the claim
gets dropped, guessed at, or bounced to someone who cannot repair it. **The expensive quantity
is the latency between a bad capture and anyone knowing it was bad** — so Second Look decides
at the moment of capture, not at month end.

A receipt-capture inspection desk for the
[OpenCV AI Competition 2026, powered by AWS](https://opencv26.devpost.com/), entered on the
**Agentic Vision** path. A phone posts a photo of an expense receipt; OpenCV 5 measures it —
document quad and rectification, per-tile focus, exposure, specular glare, text coverage,
frame-edge crop, QR/barcode, and a perceptual hash for duplicates — and a deterministic
policy turns those measurements into one of three verdicts: **accept**, **retake**, or
**escalate**.

It is **active perception for autonomous inspection**, the competition's first suggested
project area, with one twist: the system cannot move the camera, so it directs the person
holding it. A shot with glare across the total is asked to be re-taken with the light moved;
the re-take that removes the glare but clips the bottom edge gets a *different* instruction,
from a different rule, fired by a different metric, and a hint box on the region to fix. Each
retake is measured again and compared against the defect it was asked to fix. The visual
evidence changes what the system does next, and the stored trace shows exactly which
measurement caused which call.

The two ways this can be wrong don't cost the same: nagging someone for a retake they didn't
need costs a few seconds of irritation, but silently accepting an unreadable capture costs the
whole claim. So the agent auto-accepts only when every metric is comfortably inside its band
and the capture is not a suspected duplicate. The uncertain band, a defect that survived two
retakes, a suspected duplicate, and anything that does not look like a document all go to a
person — the only party who can approve, reject or resolve them. Nothing is ever sent
anywhere: no email, no accounting integration, no payment.

**Submitted** on 2026-09-17 —
[devpost.com/software/second-look-0l5bas](https://devpost.com/software/second-look-0l5bas).
**Demo video (4:01):** <https://youtu.be/j3dhhLk-Y7o>

**Try it live:** <http://32.236.165.113/> — the same server on one AWS EC2 instance in Sydney,
plain HTTP, since 2026-09-28. The page there is the review queue, empty until something
escalates. To put a card on it, run from the root of a clone
`curl -s -X POST --data-binary @data/synthetic/not_doc.jpg http://32.236.165.113/inspect` (its
JSON answers `"state": "escalated", "review_reason": "not_a_document"`), then reload the page:
the card shows the rule that fired, its table of checks and the key measurements without a
token. The photo overlay and the Approve / Reject buttons need the reviewer token, which is not
published, so the card stays in the queue until the entrant acts on it. The `curl` checks in
[Deployment](#deployment) run against it from the root of a clone (curl and python3 only).
A static replay of a recorded run is at <https://guptachetan1995.github.io/opencv/>.
**Or locally:** `make setup`, then `.venv/bin/python tools/run_demo.py` (the whole loop, printed
as its trace) or `make run` and open <http://127.0.0.1:8080/> (the review page). A live
screen-share of the review page is also available to judges on request via a Devpost message.

This README covers [what already exists](#what-already-exists-and-what-this-adds),
[how it works](#how-it-works) (the measurements, the decision cascade, the agent tools and
human verbs, the trace), [the demo](#the-demo), the [evaluation headline](#evaluation),
[setup and commands](#setup-run-test-lint), the [HTTP API](#http-api), the
[MCP server](#mcp-server-appmcp_serverpy), [deployment](#deployment), and
[what is not built](#what-is-not-built). The technical report, both diagrams and the
generated evaluation are in [`docs/`](#documentation).

**Status:** code-complete and tested locally; the same routes serve live on AWS EC2 since
2026-09-28, and the Lambda deploy is blocked by the account.

| Layer | State |
|---|---|
| `inspect()` (eight OpenCV 5 measurements) + `decide()` (rule cascade) | Built, tested against a synthetic set with exact ground truth |
| `agent_loop.py` — the agent tools and human verbs behind one `invoke(tool, args, actor)` chokepoint | Built: the actor guard refuses an agent reaching for a human verb, and each agent tool refuses a capture that has left the agent's part of the lifecycle, so no agent call can move an escalated capture |
| `overlay.py` — the evidence overlay | Built: the photo and the rectified page with every region the measurements found and the hint box, drawn per request and never stored |
| `service.py` + `app/server.py` — the HTTP routes (`make run`) | Built: inspect, retake, trace, overlay, and the three human verbs, which need the reviewer token; `app/smoke.py` (`make smoke`) exercises it end to end |
| `app/static/review.html` — the review page | Built: the overlay, the clause that fired, the key measurements, and Approve / Reject / "Is a duplicate" / "Not a duplicate" |
| `app/mcp_server.py` — a stdio MCP server over the agent tools | Built: the agent tools and reads only; the human verbs are not offered |
| `deploy/handler.py` (Lambda), the container images, [`docs/deploy.md`](./docs/deploy.md) | Lambda adapter and image: built (the image locally for `linux/arm64`, 2026-09-17). EC2 image: built on the instance's first boot, 2026-09-28, and serving |
| [`docs/evaluation.md`](./docs/evaluation.md) | Built |
| Live AWS endpoint | **EC2: live** at <http://32.236.165.113/> since 2026-09-28 — see [Deployment](#deployment). **Lambda: blocked** — the only available AWS account's Service Control Policy denies `ecr:CreateRepository` and `lambda:CreateFunction` |
| `apply.py`/`store.py` (persistence), three of the six human verbs, the browser agent lane | Not built — see [What is not built](#what-is-not-built) |

The serving paths are in-memory, matching `agent_loop.py`'s own scope; there is no
persisted store.

## What already exists, and what this adds

Capture-time quality checks are not new. Scanbot's
[Document Quality Analyzer](https://docs.scanbot.io/android/document-scanner-sdk/document-quality-analyzer/introduction/)
scores a scan by how readable its text is and returns the score with a histogram and
heatmap of text scores for the integrating app to act on. Veryfi Lens
([settings](https://docs.veryfi.com/lens/mobile/settings/)) flags a capture with 20% or more
blur and alerts the user that it may need recapturing, has optional glare detection, and
detects and crops the document during capture. Expensify's SmartScan
([troubleshooting](https://help.expensify.com/articles/expensify-classic/expenses/Troubleshoot-SmartScan-Issues))
reports a failed scan after it runs and lets the user tap Retake. Second Look takes that
pattern as its starting point. What it adds, none of which we found in the documentation
pages linked above:

- **A different, located instruction per failing metric.** Each retake names the one metric
  that failed and a hint box on the rectified page where it failed, from a committed rule
  table whose every evaluated clause is recorded in the verdict.
- **Glare judged by where it falls.** `glare_over_text_frac` is the share of the glare that
  lies on the text lines: glare on blank paper is accepted, glare across the total is not.
- **Retake memory.** `compare_captures` measures whether the defect the retake was asked to
  fix is actually `fixed`, and `persistent_defect` stops asking after two retakes and hands
  the capture to a person.
- **A duplicate check only a person can resolve.** The agent can escalate a suspected
  duplicate but can never accept or reject one; even the reviewer's approve is refused
  until they say whether it is a duplicate.
- **A `caused_by` trace behind an actor- and state-guarded chokepoint**, so which
  measurement caused which call — and which person made which decision — is a stored,
  checkable record.

## How it works

Diagrams, both drawn as built (solid = built and exercised by tests, or deployed and verified
live; dashed = planned, not built or not deployed): [`docs/architecture.svg`](./docs/architecture.svg), walked through in
[`docs/architecture.md`](./docs/architecture.md), and
[`docs/agent-workflow.svg`](./docs/agent-workflow.svg), walked through in
[`docs/agent-workflow.md`](./docs/agent-workflow.md).

The path of one capture:

```
client (browser, curl, or an MCP client)
  → app/server.py (make run, or EC2) | deploy/handler.py (Lambda) | app/mcp_server.py (stdio)
      → secondlook.service routes (HTTP adapters) → agent_loop.process_capture
          → invoke("inspect_capture", …, actor="agent")  → perception.inspect()  [OpenCV 5]
          → invoke("decide_capture",  …, actor="agent")  → policy.decide()       [11-rule cascade]
              → accept   → the capture joins the batch's accepted set
              → retake   → invoke("request_recapture", …, actor="agent") → a retake slot
              → escalate → invoke("escalate", {reason}, actor="agent") → the human review queue
```

### The eight OpenCV 5 measurements

Each measurement is one pure function in `src/secondlook/metrics.py`; `perception.inspect()`
runs them in order, times each, and returns one frozen `Measurements` record
(`src/secondlook/schema.py`). Rectification runs first and every later measurement reads the
rectified page, which is why blur and glare are reported by location on the receipt rather
than as one score for the photograph.

| # | Measurement | OpenCV 5 calls | Metrics emitted |
|---|---|---|---|
| 1 | Document quad + rectification | `Canny`, `findContours`, `approxPolyDP`, `contourArea`, with a `HoughLinesP` fallback; then `getPerspectiveTransform` + `warpPerspective` | `quad_found`, `quad`, `page_area_fraction`, `corner_confidence`, `second_quad_area_fraction` |
| 2 | Focus, per tile | `Laplacian` variance per unit of ink over a 6×8 grid; only tiles carrying ink vote | `focus_global`, `focus_min_tile`, `blur_tiles` |
| 3 | Exposure and contrast | `calcHist` | `clipped_low_frac`, `clipped_high_frac`, `contrast_p95_p5` |
| 4 | Specular glare | HSV low-saturation / high-value mask, `morphologyEx` open then close, `connectedComponentsWithStats` | `glare_area_fraction`, `glare_boxes`, `glare_over_text_frac` |
| 5 | Text presence and coverage | classical black-hat ink map (`getStructuringElement`, `morphologyEx`, `subtract`) with a Weber-contrast gate, then `connectedComponentsWithStats` | `text_box_count`, `text_coverage_fraction`, `text_median_height_px`, `bottom_band_has_text`, `text_boxes` |
| 6 | Frame-edge crop | the located quad against the frame border | `edge_touch_sides` |
| 7 | QR / barcode | `QRCodeDetector`, `barcode_BarcodeDetector` | `code_kind`, `code_decoded` |
| 8 | Duplicate | dHash over a 9×8 `resize`, Hamming distance against the batch's accepted captures | `phash`, `nearest_distance`, `duplicate_of` |

The record also carries `image_shape`, `page_shape`, `opencv_version`, `dnn_engine`,
`text_detector` and per-measurement `elapsed_ms` — 31 fields in all. Every field is a number,
a bool, a short string, or a list of boxes or points: **no pixel data and no decoded text is
ever stored in a record** (a QR payload is dropped inside the metric that read it), and
`tests/test_schema.py` asserts it.

Three measurements do more than score the image. `glare_over_text_frac` — the share of the
glare that lies on the text lines, not glare area — is what separates "glare on white space,
accept" from "glare across the total, retake". A decoded QR (`code_decoded`) cancels the
`out_of_focus` retake a soft page would otherwise get: a measurement calling an action *off*.
`second_quad_area_fraction` exists so that two receipts in one frame escalate instead of the
largest-quad heuristic silently scoring one of them.

**The evidence overlay** (`src/secondlook/overlay.py`) draws those measurements back onto the
image with OpenCV: the frame as posted with the located quad, and the page re-warped from the
stored quad onto exactly `page_shape`, with the text boxes, blur tiles, glare boxes and the
verdict's hint box, under a header quoting the clause that fired (`glare_over_text_frac 0.92
> 0.15`). It is rendered on request — `GET /overlay/<capture_id>` for the reviewer, the hero
image above, the replay site — and never written to a record.

### What OpenCV 5 changed, and what it costs this entry

- The pin is exact — `opencv-python-headless==5.0.0.93` — because `opencv-python` 4.14.x also
  exists on PyPI and a loose constraint can resolve backwards into the 4.x line.
  `tests/test_opencv_version.py` fails on a 4.x wheel, checks that the 5.x APIs this entry
  relies on exist (`CV_Bool`, `dnn.ENGINE_NEW`, `dnn.TextDetectionModel_DB`,
  `barcode_BarcodeDetector`), and checks that the removed `readNetFromCaffe` and
  `readNetFromDarknet` are gone.
- `warpPerspective`, `warpAffine` and `remap` interpolate slightly differently from 4.x, so
  **the suite has no pixel-exact baselines**: every image assertion is a tolerance against a
  property (area, distance, monotonicity).
- `cv2.ml`, `CascadeClassifier` and `HOGDescriptor` moved to contrib. The decision layer is a
  threshold table, not a trained classifier, so `opencv-contrib-python-headless` is not a
  dependency.
- With the Caffe and Darknet loaders gone, any model must be ONNX. The DNN text-detector path
  is not built and no weights are vendored ([`models/README.md`](./models/README.md));
  measurement 5 runs the classical path. No DNN model runs today; each `Measurements` record's
  `dnn_engine` field names the engine OpenCV 5 would select (`new`, unless
  `OPENCV_FORCE_DNN_ENGINE` forces `classic`), so a future DNN path reports its engine.

### The decision cascade

`policy.decide(measurements, policy)` is a pure function over the ordered rule table in
[`src/secondlook/policy.toml`](./src/secondlook/policy.toml). There is no model and no
randomness in the path that produces a verdict. Rules are evaluated top to bottom, the first
match wins, and every clause evaluated — matched or not — is recorded in the verdict's
`firings` with its metric, value, threshold and comparison, so a verdict can be audited
without reading the code.

| # | Rule | Fires when | Outcome |
|---|---|---|---|
| 1 | `not_a_document` | `quad_found == false` or `text_coverage_fraction < 0.02` | escalate |
| 2 | `two_documents` | `second_quad_area_fraction > 0.05` | escalate |
| 3 | `suspected_duplicate` | `nearest_distance <= 6` against an accepted capture | escalate |
| 4 | `persistent_defect` | `attempt >= 3` and the rest of the cascade would repeat the parent capture's reason | escalate |
| 5 | `bottom_edge_clipped` | `edge_touch_sides` contains `bottom` and `bottom_band_has_text` is true | retake |
| 6 | `glare_over_total` | `glare_over_text_frac > 0.15` | retake |
| 7 | `out_of_focus` | `focus_min_tile < 2.0` and `code_decoded == false` | retake |
| 8 | `underexposed` | `clipped_low_frac > 0.25` | retake |
| 9 | `overexposed` | `clipped_high_frac > 0.40` | retake |
| 10 | `uncertain` | a metric lies within its configured margin of one of the thresholds above | escalate (`uncertain_band`) |
| 11 | `accept` | nothing above matched | accept |

The order is the policy. Escalating rules sit above retake rules, so "this is not a receipt"
or "this receipt is already in the batch" beats "the light was bad". A suspected duplicate is
never auto-rejected; a person decides. Rule 5 needs both halves: a page touching the bottom
edge with a blank bottom band is a complete receipt, while text at the cut means the total is
outside the frame. Rule 10 exists so that "close to the line" is a person's call rather than a
hair's-width verdict.

**Why the decision layer is deterministic, not an LLM.** The same photo always gets the same
verdict, and every verdict carries the clause that produced it, so a threshold can be tested,
audited and argued with, and every verdict in the evaluation below comes out the same on every
run. Nothing leaves the
machine to decide a capture, so there is no per-photo model cost and no receipt image sent to
a third party. The judgment calls that do need intelligence — is this the same receipt, is
this blur acceptable, is this even a receipt — are exactly the ones routed to a person rather
than to a model. An LLM agent can still drive the loop, through the [MCP
server](#mcp-server-appmcp_serverpy), and the same guards bind it.

### Agent tools and human verbs

Every tool and every verb is a call into one function, `agent_loop.invoke(tool, args, actor)`,
and its first act is the actor guard (`src/secondlook/agent_loop.py`):

```python
if tool in HUMAN_VERBS and actor != "reviewer":
    raise PermissionError(f"{tool!r} is human-only; actor was {actor!r}")
if tool in AGENT_TOOLS and actor != "agent":
    raise PermissionError(f"{tool!r} is an agent tool; actor was {actor!r}")
```

The second guard is the capture's state. Each agent tool acts only on a capture that is still
`received` or `measured` (`AGENT_STATES`) and raises `StateError` for anything else — a capture
awaiting a retake photo, escalated to a person, accepted or rejected. Without it an agent could
re-decide an escalated capture back to `measured` and request a retake of it, walking it out of
the review queue with no person involved; `tests/test_agent_loop.py`
(`test_agent_tools_cannot_move_an_escalated_capture`) reproduces exactly that sequence and
asserts every agent tool is refused and the capture stays `escalated`. The human-only verbs are
never registered as agent tools, and the tests assert the two sets are disjoint.

**Agent tools** (`AGENT_TOOLS`; `actor="agent"` only):

- **`inspect_capture(capture_id)`** — runs the eight measurements on the capture's stored
  image, stores the `Measurements` record, and moves the capture from `received` to
  `measured`. It does **not** decide a verdict, ask for a retake, or accept anything. Run twice
  on the same image it gives the same numbers, as long as the batch's accepted set has not
  changed (measurement 8 compares against it).
- **`decide_capture(capture_id)`** — evaluates the cascade against the stored measurements and
  records the verdict plus every clause it evaluated. It does **not** re-run OpenCV: it raises
  if no measurement record exists. An `accept` verdict *is* the auto-accept — the capture moves
  to `accepted` and its hash joins the batch — and the cascade cannot produce `accept` for a
  suspected duplicate, because rule 3 sits above rule 11. It does **not** re-decide a capture
  that is escalated, awaiting a retake, or decided.
- **`request_recapture(capture_id)`** — for a capture whose own verdict is `retake`: records
  the metric that failed and the box on the page where it failed (both taken from the
  verdict; a caller may restate them, not replace them), opens a successor capture slot
  (`parent_id` set, `attempt` + 1), and moves the capture to `awaiting_retake`. It does
  **not** notify anyone — there is no email, SMS or push — and does **not** delete or alter
  the previous capture, which stays in the trace as evidence.
- **`compare_captures(previous_id, new_id)`** — measures the retake image and reports, for the
  one metric that failed on the previous capture, whether that defect is `fixed`, `unchanged`
  or `worse`. It does **not** decide a verdict or store measurements on the new capture
  (`inspect_capture` runs next), and does **not** vouch for the rest of the image: a fixed glare
  with a new crop reports `fixed`, and the crop is caught by the next `decide_capture`.
- **`escalate(capture_id, reason)`** — for a capture whose own verdict is `escalate`: moves it
  into the human review queue under the verdict's machine-readable reason (`not_a_document`,
  `two_documents`, `suspected_duplicate`, `persistent_defect` or `uncertain_band`). The reason
  is optional and, like `request_recapture`'s metric, may be restated but not replaced, so a
  suspected duplicate cannot be relabelled to skip the reviewer's duplicate question
  (`test_escalate_keeps_the_verdicts_reason_so_a_duplicate_cannot_be_relabelled`). It does
  **not** approve or reject anything. After it, `process_capture` is a no-op and every agent
  tool refuses the capture, so nothing advances it until a reviewer's `invoke()` call does.

**Read tools** — `get_capture(capture_id)` and `get_trace(capture_id)` — are open to either
actor, change nothing, and write no trace entry. `get_capture` returns a fresh dict built from
the record, never the live object, so editing what it returns edits nothing.

`open_capture()` and `attach_image()` are plumbing, not gated tools: a photo landing in a new
slot, or in the retake slot `request_recapture` opened. `attach_image` refuses any capture that
is not an open, unmeasured retake slot, so a photo can never be swapped under a measured one.

**Human-only verbs** (`HUMAN_VERBS`; `actor="reviewer"` only; over HTTP each needs the
reviewer token):

- **`approve(capture_id, note)`** — accepts an escalated capture. It refuses a
  `suspected_duplicate` until `resolve_duplicate` has cleared it, so a possible duplicate cannot
  be waved through in one click. `POST /approve/<capture_id>`, the review page's Approve button.
- **`reject(capture_id, note)`** — refuses an escalated capture. `POST /reject/<capture_id>`,
  the Reject button.
- **`resolve_duplicate(capture_id, is_duplicate, note)`** — the arbiter for measurement 8:
  `is_duplicate=True` rejects the capture; `False` clears it and leaves it waiting for
  `approve`. `POST /resolve_duplicate/<capture_id>`, the "Is a duplicate" and "Not a duplicate"
  buttons.

`override` (overturn a verdict), `discard` (irreversibly delete a capture) and `close_batch`
are designed as human-only verbs too, and are not built.

### The trace

Every `invoke()` call appends a `TraceEntry(seq, at, actor, action, inputs, outputs,
caused_by)` to the capture. `actor` is `agent` or `reviewer` — the field the human gate is
audited through — and `inputs` / `outputs` hold metric values and identifiers, never pixels.
`caused_by` is the `seq` of the entry whose output chose this action; it is what turns the trace
from a log into evidence that a measurement chose the next call. `AgentLoop.trace_chain()`
walks `parent_id` back to the first capture and numbers the whole retake chain as one sequence,
so `caused_by` crosses from a retake request to the retake that answered it.
`GET /trace/<capture_id>` returns that chain.

## The demo

`tools/run_demo.py` drives the loop against the committed synthetic images, in one process
with no server, and prints the stored trace. Real output of `.venv/bin/python tools/run_demo.py`:

```
glare_text.jpg -> awaiting_retake (glare_over_total): Glare is covering the text. Move so the light source is behind you and shoot again.
crop_bottom.jpg (retake) -> awaiting_retake (bottom_edge_clipped): The bottom of the receipt is outside the frame. Step back and include the total line.

-- trace: glare -> crop retake chain --
seq  actor    action             inputs -> outputs (caused_by)
  1  agent    inspect_capture    {'image_shape': [1600, 1200]} -> {'phash': '174e787070788680', 'nearest_distance': 64}  (caused_by=None)
  2  agent    decide_capture     {'glare_over_text_frac': 0.9211} -> {'outcome': 'retake', 'rule_id': 'glare_over_total', 'reason_code': 'glare_over_total'}  (caused_by=1)
  3  agent    request_recapture  {'failing_metric': 'glare_over_text_frac'} -> {'hint_box': [201, 1006, 462, 141], 'successor_id': 'c_002'}  (caused_by=2)
  4  agent    compare_captures   {'metric': 'glare_over_text_frac', 'before': 0.9211} -> {'after': 0.0, 'status': 'fixed'}  (caused_by=3)
  5  agent    inspect_capture    {'image_shape': [1600, 1200]} -> {'phash': '330e7c3870707058', 'nearest_distance': 64}  (caused_by=4)
  6  agent    decide_capture     {'edge_touch_sides': ['bottom'], 'bottom_band_has_text': True} -> {'outcome': 'retake', 'rule_id': 'bottom_edge_clipped', 'reason_code': 'bottom_edge_clipped'}  (caused_by=5)
  7  agent    request_recapture  {'failing_metric': 'edge_touch_sides'} -> {'hint_box': [0, 895, 800, 122], 'successor_id': 'c_003'}  (caused_by=6)
clean_a.jpg -> accepted
clean_b.jpg -> accepted
dup_a.jpg -> escalated (suspected_duplicate): This looks like a receipt already in the batch. A person will decide.
reviewer resolves + approves -> accepted

-- trace: escalation, resolved and approved --
seq  actor    action             inputs -> outputs (caused_by)
  1  agent    inspect_capture    {'image_shape': [1600, 1200]} -> {'phash': '174c7070785d0680', 'nearest_distance': 3}  (caused_by=None)
  2  agent    decide_capture     {'nearest_distance': 3} -> {'outcome': 'escalate', 'rule_id': 'suspected_duplicate', 'reason_code': 'suspected_duplicate'}  (caused_by=1)
  3  agent    escalate           {'reason': 'suspected_duplicate'} -> {'review_item': 'opened'}  (caused_by=2)
  4  reviewer resolve_duplicate  {'is_duplicate': False, 'note': 'two different lunches'} -> {'duplicate': 'cleared'}  (caused_by=3)
  5  reviewer approve            {'note': 'confirmed by reviewer'} -> {'state': 'accepted'}  (caused_by=4)

second look demo: all beats reached their expected verdict.
```

Read the `caused_by` column of the first trace. Entry 3's retake request was chosen by entry
2's decision, which was chosen by entry 1's measurement (`glare_over_text_frac` 0.9211 — 92% of
the glare lies on the text lines — over the 0.15 threshold). The retake, `crop_bottom.jpg`, is
the same receipt with the light moved: entry 4 reports the glare `fixed` (0.9211 to 0.0). But
its bottom edge is off the frame with text at the cut, so entry 6 fires a **different rule on a
different metric**, `bottom_edge_clipped`. Nothing scheduled that second instruction; the
second image's own measurements chose it. That is the Agentic Vision qualifying beat.

In the second trace, `dup_a.jpg` lands at Hamming distance 3 from the already-accepted
`clean_a.jpg`, so the agent escalates it and cannot accept it; only the two `reviewer` entries
move it to `accepted`. The demo's reviewer clears the duplicate to show the approve path.
`dup_a.jpg` is in fact the same receipt re-shot, so the evaluation harness resolves the same
fixture as a real duplicate and rejects it. The script asserts its own beats, and
`tests/test_agent_loop.py` runs it and checks each beat's verdict appears in the output.

**The same loop over HTTP.** `POST /inspect` returns the retake slot (`successor_id`) a retake
verdict opened, and `POST /retake/<successor_id>` posts the retake photo into it. Real output
against `make run` (each capture response piped through a one-line selector printing
`capture_id state rule_id successor`; the `401` refusal is shown as returned):

```
$ curl -s -X POST --data-binary @data/synthetic/glare_text.jpg $BASE/inspect
c_001 awaiting_retake glare_over_total successor: c_002
$ curl -s -X POST --data-binary @data/synthetic/crop_bottom.jpg $BASE/retake/c_002
c_002 awaiting_retake bottom_edge_clipped successor: c_003
$ curl -s -X POST --data-binary @data/synthetic/clean_a.jpg $BASE/retake/c_003
c_003 accepted accept successor: None
$ curl -s -X POST --data-binary @data/synthetic/not_doc.jpg $BASE/inspect
c_004 escalated not_a_document successor: None
$ curl -s -X POST -d '{"note": "not a receipt"}' $BASE/reject/c_004
{"error": "reviewer token required"}
$ curl -s -X POST -H "Authorization: Bearer $REVIEWER_TOKEN" -d '{"note": "not a receipt"}' $BASE/reject/c_004
c_004 rejected not_a_document successor: None
```

`GET /trace/c_003` then returns all ten entries of the chain, from the first glare
measurement to the accept, with `compare_captures` reporting the glare and then the crop
`fixed`.

## Evaluation

[`docs/evaluation.md`](./docs/evaluation.md) is generated by
`.venv/bin/python -m eval.run_eval`, which runs the committed synthetic set (17 samples, seed
20260908, exact ground truth by construction) through the same `invoke()` chokepoint. Headline
numbers: task success **15/15**, silent-accept rate **0/15** — the number this entry is built
around, since a silently accepted bad capture is the one error that costs the claim — and
retake convergence **5/6**, where the sixth sequence (`blur_4` three times) correctly stops at
`persistent_defect`.

Those are the isolated numbers, one receipt per batch, which is how the ground truth was
written. **Through one shared batch, task success is 9/15**: receipts that share a printed
layout collide as suspected duplicates of one already accepted — `glare_text.jpg` posted after
`clean_a.jpg` in the same batch escalates as `suspected_duplicate` instead of asking for a
retake. The silent-accept rate stays **0/15** in the shared batch too: every collision goes to a
person. The report names four failure cases and five limitations of the evaluation itself,
starting with the fact that there is no real-photograph set yet (the collection protocol is
[`docs/real-photo-set.md`](./docs/real-photo-set.md), and the harness scores set R the moment
`data/real/manifest.json` exists). The technical report
([`docs/report.md`](./docs/report.md) § 7) adds one capability limit no number covers: a
photograph of a screen showing a receipt (moiré) is not detected.

## Stack

- Python 3.13; the Lambda image is `public.ecr.aws/lambda/python:3.13` (arm64 / Graviton2), the
  EC2 image is `python:3.13-slim` (`deploy/ec2/Dockerfile`)
- `opencv-python-headless==5.0.0.93` — OpenCV 5.0.0; the pin is exact because
  `opencv-python` 4.14.x also exists and a loose constraint resolves backwards into the 4.x
  line, where the warping numerics differ
- `numpy==2.5.3`
- `pytest==9.1.1`, `ruff==0.16.6`, `Pillow==12.3.0` (dev only; Pillow is not in either image)
- One static HTML page, vanilla JavaScript — no framework, no bundler
- MCP over stdio, written against the standard library — no SDK dependency
- AWS: one EC2 `t3.micro` in `ap-southeast-2` running the same routes (live), and a Lambda
  container image behind a Lambda Function URL (built, blocked by the account). The S3 store and
  the structured CloudWatch trace logs are designed but not built. **Not AWS App Runner**, which
  [closed to new customers on 30 April 2026](https://aws.amazon.com/apprunner/).

The runtime dependency set is exactly two packages: `opencv-python-headless` and `numpy`
(`requirements.txt`, hashed in `requirements.lock`). The development set adds the test runner,
linter and sample renderer (`requirements-dev.txt`, hashed in `requirements-dev.lock`). Both
locks are generated by `pip-compile --generate-hashes` and installed with `--require-hashes`.
`opencv-contrib-python-headless` is deliberately not a dependency.

## Setup, run, test, lint

Needs `python3.13` on the `PATH` (pyenv reads `.python-version`; otherwise pass
`PY=/path/to/python3.13` to `make`). Everything runs offline after `make setup`.

```sh
git clone https://github.com/guptachetan1995/opencv && cd opencv
make setup     # python3.13 -m venv .venv && pip install --require-hashes -r requirements-dev.lock
make test      # pytest — metrics, policy, schema, samples, OpenCV version, agent loop, HTTP, MCP
make lint      # ruff check . && ruff format --check .
make samples   # regenerate data/synthetic/ from the fixed seed
bash verify.sh # the single gate: README and licence checks + lint + tests
```

```sh
make run      # python3 app/server.py — binds 127.0.0.1:8080 (HOST and PORT override)
make smoke    # python3 app/smoke.py — starts its own copy, hits /health + one /inspect
```

`make run` prints a reviewer token for the run (or set `REVIEWER_TOKEN` to choose one, which is
then never echoed); paste it into the review page's token field to see the photos and act on
the queue.

```sh
.venv/bin/python tools/run_demo.py        # the demo above, end to end
.venv/bin/python -m eval.run_eval         # regenerates docs/evaluation.md from the committed set
.venv/bin/python tools/make_hero.py       # redraws docs/hero.jpg from a real run
./build-pages.sh /tmp/second-look-site    # the static replay site of a recorded run
.venv/bin/python app/mcp_server.py        # the stdio MCP server (an MCP client starts it)
```

Using the pipeline from Python:

```python
from secondlook import decide, inspect_file, load_policy

policy = load_policy()  # src/secondlook/policy.toml
record = inspect_file("data/synthetic/glare_text.jpg")  # Measurements (schema.py)
verdict = decide(record, policy)  # Verdict (schema.py)
print(verdict.outcome, verdict.rule_id, verdict.hint_box)
# retake glare_over_total [x, y, w, h]
```

Or the agent loop, where the verdict above picks the next `invoke()` call instead of you:

```python
from secondlook.agent_loop import AgentLoop, invoke, process_capture

loop = AgentLoop()
capture_id = loop.open_capture("data/synthetic/glare_text.jpg")
capture = process_capture(capture_id, loop=loop)  # inspect -> decide -> request_recapture
print(capture.state, capture.verdict.rule_id)
# awaiting_retake glare_over_total

# ... a retake photo arrives at the slot request_recapture opened ...
successor_id = capture.trace[-1].outputs["successor_id"]
loop.attach_image(successor_id, "data/synthetic/crop_bottom.jpg")
retake = process_capture(successor_id, loop=loop)
print(retake.state, retake.verdict.rule_id)  # a DIFFERENT rule: bottom_edge_clipped

# an escalation waits until a human calls invoke() with actor="reviewer"
invoke("approve", {"capture_id": "..."}, "reviewer", loop=loop)
```

## HTTP API

The routes live once, in `src/secondlook/service.py`, and two adapters serve them:
`app/server.py` (the standard library's `http.server`: `make run` locally, and the EC2 image)
and `deploy/handler.py` (a Lambda Function URL). No framework, since the runtime dependency set
is exactly OpenCV and numpy. One process, one in-memory loop; state does not survive a restart.

| Route | What |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `POST /inspect` | body: raw image bytes. Runs `process_capture` (inspect -> decide -> the next call the verdict picks) and returns the capture: `state`, `measurements`, `verdict`, and `successor_id` when a retake was requested. A body over 4 MB is rejected with `413 {"error": "payload_too_large"}`. |
| `POST /retake/<successor_id>` | body: raw image bytes for the retake slot a retake verdict opened; runs the same loop, starting with `compare_captures` against the previous capture. `409` for anything that is not an open retake slot. |
| `GET /capture/<capture_id>` | one capture (the `get_capture` read tool) |
| `GET /trace/<capture_id>` | the capture's full ordered trace across its retake chain (see [The trace](#the-trace)) |
| `GET /pending` | captures currently `state == "escalated"`, waiting for a reviewer |
| `GET /overlay/<capture_id>` | **reviewer token.** The evidence overlay JPEG, drawn for this request. `410` once the photo is no longer held. |
| `POST /approve/<capture_id>` | **reviewer token.** Body: optional `{"note": str}`. `invoke("approve", ..., actor="reviewer")`. |
| `POST /reject/<capture_id>` | **reviewer token.** Body: optional `{"note": str}`. `invoke("reject", ..., actor="reviewer")`. |
| `POST /resolve_duplicate/<capture_id>` | **reviewer token.** Body: `{"is_duplicate": true or false, "note": str}`. |
| `GET /`, `GET /review` | the review page (`app/static/review.html`) — its buttons `fetch()` the reviewer routes above |

**The reviewer is authenticated, not just named.** The reviewer routes need
`Authorization: Bearer <reviewer token>` and answer `401` without it, before any `invoke()` is
made. The token is `REVIEWER_TOKEN`, or one `make run` generates and prints; the Lambda adapter
takes it only from `REVIEWER_TOKEN` and keeps the routes closed without one. The review page
keeps the token in the tab's `sessionStorage`. The agent's own `actor="agent"` path never has
the token and never reaches these verbs.

**Photos.** An upload is deleted as soon as the loop has read it, unless the capture escalated:
then it is held, in the server's temporary directory and never in a record, so the reviewer can
see it, and deleted the moment the capture leaves the review queue. At most 64 are held; past
that the oldest is deleted and its overlay answers `410`.

```sh
make run &
curl -s http://127.0.0.1:8080/health
curl -s -X POST --data-binary @data/synthetic/not_doc.jpg \
  -H 'Content-Type: image/jpeg' http://127.0.0.1:8080/inspect
# open http://127.0.0.1:8080/, paste the printed reviewer token, and reject or approve it
```

## MCP server (`app/mcp_server.py`)

A stdio MCP server that lets an LLM agent drive the same loop. It offers the agent tools
(`inspect_capture`, `decide_capture`, `request_recapture`, `compare_captures`, `escalate`), the
reads (`get_capture`, `get_trace`), `open_capture` and `attach_retake` for getting a local photo
into a slot, and `run_loop` (the deterministic `process_capture`). Every agent tool and read is
the same `invoke(..., actor="agent")` the loop makes, so the same state guards apply: an agent
calling `decide_capture` on an escalated capture gets a `StateError`, not a new verdict.
`open_capture` and `attach_retake` decide nothing and sit outside `invoke`, exactly as
`POST /inspect` and `POST /retake` do: they are the same photo-arrival plumbing
(`AgentLoop.open_capture`, `AgentLoop.attach_image`), and `attach_image` only fills an open,
unmeasured retake slot. A JSON-RPC batch (an array) is answered `-32600 Invalid Request`. The human
verbs are not offered, and a call to one is refused as an unknown tool. Every tool description
says what the tool does not do. Standard library only: newline-delimited JSON-RPC on
stdin/stdout, protocol versions 2024-11-05 through 2025-11-25.

Client configuration (absolute paths): command `<clone>/.venv/bin/python`, args
`["<clone>/app/mcp_server.py"]`. `tests/test_mcp_server.py` drives it over stdio.

## Layout

```
src/secondlook/
  schema.py       Measurements / Verdict / RuleFiring / TraceEntry — the structured results
  metrics.py      one pure function per measurement
  perception.py   inspect(): rectify first, then the other seven, timed
  policy.py       decide(): the cascade, first match wins, every clause recorded
  policy.toml     the committed threshold table and perception parameters
  agent_loop.py   invoke(tool, args, actor) chokepoint + state guards + process_capture driver
  overlay.py      the evidence overlay, drawn with OpenCV per request
  service.py      the HTTP routes, the reviewer-token check, the held-photo rule
app/
  server.py       the stdlib HTTP adapter (make run, EC2)
  mcp_server.py   the stdio MCP adapter over the agent tools
  smoke.py        the smoke command: starts its own server, hits /health + one /inspect
  static/review.html   the review page; its buttons call the same invoke() the tools call
deploy/
  handler.py      the Lambda Function URL adapter, same routes as server.py
  Dockerfile      arm64 Lambda container image on public.ecr.aws/lambda/python:3.13
  build.sh        local image build — no AWS credential needed
  deploy.sh       ECR push + function create/update + Function URL (owner-run only)
  ec2/Dockerfile  the EC2 image: app/server.py on python:3.13-slim
  ec2/user-data.sh     the EC2 first-boot script (clones this repo, builds, runs on port 80)
  smoke_local.py  runs the Lambda handler in-process against a committed sample
  iam-policy.json the permissions deploy.sh needs
eval/run_eval.py        the evaluation harness; writes docs/evaluation.md
tools/make_samples.py   the synthetic-set generator (seed 20260908)
tools/run_demo.py       runs the demo end to end, prints the trace
tools/make_hero.py      draws docs/hero.jpg from a real run
tools/build_replay.py   builds the static replay site of a recorded run (build-pages.sh)
data/synthetic/         17 samples + manifest.json ground truth + LICENSE (MIT)
models/README.md        no weights vendored; the classical text path is the default
docs/                   report, submission copy, diagrams, evaluation, deploy runbook,
                        video script, real-photo protocol, hero image
tests/                  metrics, policy, schema, samples, OpenCV version, agent loop, overlay,
                        HTTP, Lambda adapter, MCP, evaluation, replay
```

## Deployment

**Live endpoint: <http://32.236.165.113/>** (plain HTTP), since 2026-09-28. One EC2 `t3.micro`
(Amazon Linux 2023, x86_64) named `secondlook-demo`, in `ap-southeast-2` (Sydney), runs
`app/server.py` — the same routes and review page as `make run`, with the OpenCV 5 pipeline and
the agent loop behind them — in a container built from `deploy/ec2/Dockerfile` on first boot by
`deploy/ec2/user-data.sh`, which clones this public repository. Its security group admits only
TCP 80; there is no key pair and no SSH. The reviewer routes need a token generated on the
instance, which is not published. The owner launched it through the AWS console after reviewing
every field listed in [`docs/deploy.md`](./docs/deploy.md#ec2-console-deploy).

The checks below run from the root of a clone with curl and python3 only. Capture ids are
assigned in arrival order, so they take the ids from your own `/inspect` response:

```sh
BASE=http://32.236.165.113
curl -s -w '\n' "$BASE/health"
R=$(curl -s -X POST --data-binary @data/synthetic/glare_text.jpg "$BASE/inspect")
echo "$R" | python3 -c 'import json,sys; d=json.load(sys.stdin); v=d["verdict"]; print(d["capture_id"], d["state"], v["rule_id"], v["hint_box"], "successor:", d["successor_id"])'
ID=$(echo "$R" | python3 -c 'import json,sys; print(json.load(sys.stdin)["capture_id"])')
SLOT=$(echo "$R" | python3 -c 'import json,sys; print(json.load(sys.stdin)["successor_id"])')
curl -s -X POST --data-binary @data/synthetic/crop_bottom.jpg "$BASE/retake/$SLOT" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["capture_id"], d["state"], d["verdict"]["rule_id"])'
curl -s -w ' %{http_code}\n' -X POST -d '{}' "$BASE/approve/$ID"
curl -s -o /dev/null -w '%{time_total}s\n' "$BASE/health"
```

On 2026-09-28, run from the repository root against the fresh instance, where those ids were
`c_001` and `c_002`, the same checks printed exactly:

```
{"status": "ok"}
c_001 awaiting_retake glare_over_total [201, 1006, 462, 141] successor: c_002
c_002 awaiting_retake bottom_edge_clipped
{"error": "reviewer token required"} 401
0.883478s
```

That is the local expected output line for line, hint box included: the glare photo gets a
retake, the retake gets a different rule, and an approve without the token is refused with
`401`. The last line is one `/health` round trip from Bengaluru to Sydney, informational only.
If an earlier visitor had `clean_a.jpg` accepted on the instance, `glare_text.jpg` is escalated
as `suspected_duplicate` instead (that rule ranks above glare in the cascade), so there is no
retake slot and the retake line fails; `tools/run_demo.py` runs the same chain locally on a
fresh loop. Also observed then: `GET /pending`
answered `[]`, `GET /` served the review page, `GET /trace/c_001` returned the stored trace
(`inspect_capture`, then `decide_capture` with `glare_over_text_frac` 0.9211 choosing the
`glare_over_total` retake, then `request_recapture`), and `GET /overlay/c_001` answered `401`
without the token. The review-page check with the token (step 4 in `docs/deploy.md`) is the
owner's and is not yet recorded. A live screen-share of the review page is available to judges
on request via a Devpost message.

The address holds while the instance is not stopped (there is no Elastic IP), and state is in
memory, so a container restart empties the batch. Teardown after judging ends on 9 Nov 2026:
terminate the instance, then delete its security group.

**Lambda: built, blocked, not pending.** The designed target is one AWS Lambda function,
packaged as a container image on arm64 (Graviton2), 2048 MB, Python 3.13, behind a Lambda
Function URL — no load balancer, no API Gateway, nothing billing while idle. The only AWS
account available for this submission is a Free Plan "Project" whose Organization-level Service
Control Policy denied `ecr:CreateRepository` and `lambda:CreateFunction` outright when it was
tried in `us-east-1`, on both the container path and a sized-and-verified `.zip` fallback. The
attempt log with the real AWS errors is in [`docs/deploy.md`](./docs/deploy.md).
`deploy/deploy.sh` is committed and idempotent, now also requires `REVIEWER_TOKEN`, and no
automation runs it. That block is why the live endpoint is on EC2: another project in the same
AWS organization had been deployed to EC2 in `ap-southeast-2` through the console on
2026-09-11, so the same path was taken here.

Considered and rejected: **AWS App Runner** — "will no longer accept new customers starting on
April 30, 2026" (<https://aws.amazon.com/apprunner/>); **Amazon ECS Express Mode** — an
Application Load Balancer plus an always-running Fargate task billing at zero traffic, and a
documented continuous-deployment path through GitHub Actions, which this repository does not
use; **API Gateway** — a Function URL already gives HTTPS and public access.

## What is not built

Stated here so nothing above reads as a claim it isn't:

- `apply.py` / `store.py` — S3-backed persistence. State is in memory, so a restart or a new
  Lambda execution environment starts with an empty batch.
- Structured CloudWatch logging, one line per trace entry.
- `src/secondlook/handler.py` — `deploy/handler.py` is the working Lambda adapter.
- The browser *agent lane* (a page with a drop zone and a verdict panel). The review lane,
  `app/static/review.html`, is built; photos are posted with `curl`, the demo script or MCP.
- The `override`, `discard` and `close_batch` human verbs.
- The DNN text detector (`dnn.TextDetectionModel_DB` over ONNX weights).
- A real-photograph evaluation set (`data/real/`); its protocol is written
  ([`docs/real-photo-set.md`](./docs/real-photo-set.md)), the photos are not.
- HTTPS for the EC2 path: it serves plain HTTP on port 80, so the reviewer token keeps the
  review routes from casual callers, not from someone watching the network.

## Documentation

| Document | What |
|---|---|
| [`docs/report.md`](./docs/report.md) | the technical report: problem, users, architecture, OpenCV 5 implementation, AWS deployment, evaluation, limitations, responsible use |
| [`docs/submission.md`](./docs/submission.md) | the Devpost write-up and the submission status |
| [`docs/architecture.md`](./docs/architecture.md) | architecture diagram ([`.svg`](./docs/architecture.svg), [`.mmd`](./docs/architecture.mmd)) — OpenCV 5 and AWS components, drawn as built |
| [`docs/agent-workflow.md`](./docs/agent-workflow.md) | agent workflow diagram ([`.svg`](./docs/agent-workflow.svg), [`.mmd`](./docs/agent-workflow.mmd)) — perception, decision, action, and the human lane |
| [`docs/evaluation.md`](./docs/evaluation.md) | generated evaluation report: task success (isolated and shared batch), failure cases, limitations |
| [`docs/real-photo-set.md`](./docs/real-photo-set.md) | the protocol for the real-photograph set (not yet collected) |
| [`docs/deploy.md`](./docs/deploy.md) | the deployment runbook: the EC2 console deploy (live, with its verification output) and Lambda (blocked) |
| [`docs/video-script.md`](./docs/video-script.md) | the script and shot list for the demo video |

## Licence

MIT — see [`LICENSE`](./LICENSE).

The sample data is synthetic and ours: `tools/make_samples.py` renders it from a fixed seed,
and it is MIT (`data/synthetic/LICENSE`). No real photographs and no model weights are
shipped. A real set, if one is added, will be owner-shot under the protocol in
[`docs/real-photo-set.md`](./docs/real-photo-set.md), or [CORD](https://github.com/clovaai/cord)
under CC BY 4.0 with attribution.
