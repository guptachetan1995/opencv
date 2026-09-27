# Second Look

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

What makes it agentic rather than a filter is that the measurements choose the *next* action.
A shot with glare across the total is asked to be re-taken with the light moved; the re-take
that removes the glare but clips the bottom edge gets a *different* instruction, from a
different rule, fired by a different metric. The visual evidence changes what the system does
next, and the stored trace shows exactly which measurement caused which call.

The two ways this can be wrong don't cost the same: nagging someone for a retake they didn't
need costs a few seconds of irritation, but silently accepting an unreadable capture costs the
whole claim. So the agent auto-accepts only when every metric is comfortably inside its band
and the capture is not a suspected duplicate. The uncertain band, a defect that survived two
retakes, a suspected duplicate, and anything that does not look like a document all go to a
person — who is also the only party that can discard a capture or overturn a verdict. Nothing
is ever sent anywhere: no email, no accounting integration, no payment.

**Submitted** on 2026-09-17 —
[devpost.com/software/second-look-0l5bas](https://devpost.com/software/second-look-0l5bas).
**Demo video:** <https://youtu.be/zOfV23uB8Ts>

This README covers [how it works](#how-it-works) (the measurements, the decision cascade, the
agent tools and human verbs, the trace), [the demo](#the-demo), the
[evaluation headline](#evaluation), [setup and commands](#setup-run-test-lint),
[deployment](#deployment), and [what is not built](#what-is-not-built). The technical report,
both diagrams and the generated evaluation are in [`docs/`](#documentation).

**Status:** code-complete and tested locally; the live AWS endpoint is blocked, not pending.

| Layer | State |
|---|---|
| `inspect()` (eight OpenCV 5 measurements) + `decide()` (rule cascade) | Built, tested against a synthetic set with exact ground truth |
| `agent_loop.py` — the agent tools and human verbs behind one `invoke(tool, args, actor)` chokepoint | Built: `process_capture` lets the OpenCV verdict pick the next tool call, a human-approval wait resumes only on a real `invoke()` call, and the trace links every call to the entry that caused it (`python tools/run_demo.py` runs it end to end) |
| `app/server.py` — local HTTP serving (`make run`) | Built: the approval page's Approve button calls the exact same `invoke("approve", ...)` the tools call; `app/smoke.py` (`make smoke`) exercises it end to end |
| `deploy/handler.py`, the container image, [`docs/deploy.md`](./docs/deploy.md) | Built |
| [`docs/evaluation.md`](./docs/evaluation.md) | Built |
| Live AWS deploy | **Blocked, not pending** — the only available AWS account's own Service Control Policy denies both `ecr:CreateRepository` and `lambda:CreateFunction`; see [Deployment](#deployment) |
| `apply.py`/`store.py` (persistence), `overlay.py` (evidence image), three of the six human verbs | Not built — see [What is not built](#what-is-not-built) |

Both serving paths (`app/server.py` and `deploy/handler.py`) are in-memory, matching
`agent_loop.py`'s own scope; there is no persisted store.

## How it works

Diagrams, both drawn as built (solid = built and exercised by tests, dashed = planned, not
built): [`docs/architecture.svg`](./docs/architecture.svg), walked through in
[`docs/architecture.md`](./docs/architecture.md), and
[`docs/agent-workflow.svg`](./docs/agent-workflow.svg), walked through in
[`docs/agent-workflow.md`](./docs/agent-workflow.md).

The path of one capture:

```
client (browser or curl)
  → app/server.py (local, make run)  |  deploy/handler.py (AWS Lambda Function URL)
      → agent_loop.process_capture
          → invoke("inspect_capture", …, actor="agent")  → perception.inspect()  [OpenCV 5]
          → invoke("decide_capture",  …, actor="agent")  → policy.decide()       [11-rule cascade]
              → accept   → the capture joins the batch's accepted set
              → retake   → invoke("request_recapture", {failing_metric, hint_box}, actor="agent")
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
ever stored** (a QR payload is dropped inside the metric that read it), and
`tests/test_schema.py` asserts it.

Three measurements do more than score the image. `glare_over_text_frac` — glare intersected
with the text mask, not glare area — is what separates "glare on white space, accept" from
"glare across the total, retake". A decoded QR (`code_decoded`) cancels the `out_of_focus`
retake a soft page would otherwise get: a measurement calling an action *off*.
`second_quad_area_fraction` exists so that two receipts in one frame escalate instead of the
largest-quad heuristic silently scoring one of them.

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

### Agent tools and human verbs

Every tool and every verb is a call into one function, `agent_loop.invoke(tool, args, actor)`,
and its first act is the actor guard (`src/secondlook/agent_loop.py`):

```python
if tool in HUMAN_VERBS and actor != "reviewer":
    raise PermissionError(f"{tool!r} is human-only; actor was {actor!r}")
if tool in AGENT_TOOLS and actor != "agent":
    raise PermissionError(f"{tool!r} is an agent tool; actor was {actor!r}")
```

The agent has no private path to the accepted state, and the human-only verbs are never
registered as agent tools — `tests/test_agent_loop.py` asserts the two sets are disjoint.

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
  suspected duplicate, because rule 3 sits above rule 11.
- **`request_recapture(capture_id, failing_metric, hint_box)`** — records a retake request
  naming the one metric that failed and the box on the page where it failed, opens a successor
  capture slot (`parent_id` set, `attempt` + 1), and moves the capture to `awaiting_retake`. It
  does **not** notify anyone — there is no email, SMS or push — and does **not** delete or
  alter the previous capture, which stays in the trace as evidence.
- **`compare_captures(previous_id, new_id)`** — measures the retake image and reports, for the
  one metric that failed on the previous capture, whether that defect is `fixed`, `unchanged`
  or `worse`. It does **not** decide a verdict or store measurements on the new capture
  (`inspect_capture` runs next), and does **not** vouch for the rest of the image: a fixed glare
  with a new crop reports `fixed`, and the crop is caught by the next `decide_capture`.
- **`escalate(capture_id, reason)`** — moves the capture into the human review queue with a
  machine-readable reason (`not_a_document`, `two_documents`, `suspected_duplicate`,
  `persistent_defect` or `uncertain_band`). It does **not** approve or reject anything. An
  escalated capture is waiting for a person: `process_capture` is a no-op once
  `state == "escalated"`, so nothing advances it until a reviewer's `invoke()` call does.

**Read tools** — `get_capture(capture_id)` and `get_trace(capture_id)` — are open to either
actor, change nothing, and write no trace entry.

**Human-only verbs** (`HUMAN_VERBS`; `actor="reviewer"` only):

- **`approve(capture_id, note)`** — accepts an escalated capture. It refuses a
  `suspected_duplicate` until `resolve_duplicate` has cleared it, so a possible duplicate cannot
  be waved through in one click. Over HTTP this is `POST /approve/<capture_id>`, the review
  page's Approve button.
- **`reject(capture_id, note)`** — refuses an escalated capture.
- **`resolve_duplicate(capture_id, is_duplicate, note)`** — the arbiter for measurement 8:
  `is_duplicate=True` rejects the capture; `False` clears it and leaves it waiting for
  `approve`. It has no HTTP route yet; the demo and the evaluation call it through `invoke()`.

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
2's decision, which was chosen by entry 1's measurement (`glare_over_text_frac` 0.9211, over
the 0.15 threshold). The retake, `crop_bottom.jpg`, is the same receipt with the light moved:
entry 4 reports the glare `fixed` (0.9211 to 0.0). But its bottom edge is off the frame with
text at the cut, so entry 6 fires a **different rule on a different metric**,
`bottom_edge_clipped`. Nothing scheduled that second instruction; the second image's own
measurements chose it. That is the Agentic Vision qualifying beat.

In the second trace, `dup_a.jpg` lands at Hamming distance 3 from the already-accepted
`clean_a.jpg`, so the agent escalates it and cannot accept it; only the two `reviewer` entries
move it to `accepted`. The demo's reviewer clears the duplicate to show the approve path.
`dup_a.jpg` is in fact the same receipt re-shot, so the evaluation harness resolves the same
fixture as a real duplicate and rejects it. The script asserts its own beats, and
`tests/test_agent_loop.py` runs it and checks each beat's verdict appears in the output.

The same loop runs over HTTP with `make run`; see [HTTP API](#http-api-appserverpy).

## Evaluation

[`docs/evaluation.md`](./docs/evaluation.md) is generated by
`.venv/bin/python -m eval.run_eval`, which runs the committed synthetic set (17 samples, seed
20260908, exact ground truth by construction) through the same `invoke()` chokepoint. Headline
numbers: task success **15/15**, silent-accept rate **0/15** — the number this entry is built
around, since a silently accepted bad capture is the one error that costs the claim — and
retake convergence **5/6**, where the sixth sequence (`blur_4` three times) correctly stops at
`persistent_defect`. The report also names four failure cases and five limitations of the
evaluation itself, starting with the fact that there is no real-photograph set yet. The
technical report ([`docs/report.md`](./docs/report.md) § 7) adds one capability limit no number
covers: a photograph of a screen showing a receipt (moiré) is not detected.

## Stack

- Python 3.13 on `public.ecr.aws/lambda/python:3.13` (arm64 / Graviton2)
- `opencv-python-headless==5.0.0.93` — OpenCV 5.0.0; the pin is exact because
  `opencv-python` 4.14.x also exists and a loose constraint resolves backwards into the 4.x
  line, where the warping numerics differ
- `numpy==2.5.3`
- `pytest==9.1.1`, `ruff==0.16.6`, `Pillow==12.3.0` (dev only; Pillow is not in the Lambda
  image)
- One static HTML page, vanilla JavaScript — no framework, no bundler
- AWS Lambda container image behind a Lambda Function URL. The S3 store and the structured
  CloudWatch trace logs are designed but not built. **Not AWS App Runner**, which
  [closed to new customers on 30 April 2026](https://aws.amazon.com/apprunner/) — see
  [Deployment](#deployment) for why ECS Express Mode was also considered and rejected.

The Lambda runtime dependency set is exactly two packages: `opencv-python-headless` and
`numpy` (`requirements.txt`, hashed in `requirements.lock`). The development set adds the
test runner, linter and sample renderer (`requirements-dev.txt`, hashed in
`requirements-dev.lock`). Both locks are generated by `pip-compile --generate-hashes` and
installed with `--require-hashes`. `opencv-contrib-python-headless` is deliberately not a
dependency.

## Setup, run, test, lint

Needs `python3.13` on the `PATH` (pyenv reads `.python-version`; otherwise pass
`PY=/path/to/python3.13` to `make`). Everything runs offline after `make setup`.

```sh
git clone https://github.com/guptachetan1995/opencv && cd opencv
make setup     # python3.13 -m venv .venv && pip install --require-hashes -r requirements-dev.lock
make test      # pytest — metrics, policy, schema, samples, OpenCV version, agent loop, HTTP
make lint      # ruff check . && ruff format --check .
make samples   # regenerate data/synthetic/ from the fixed seed
bash verify.sh # the single gate: README and licence checks + lint + tests
```

```sh
make run      # python3 app/server.py — binds 127.0.0.1:8080 (PORT env var overrides)
make smoke    # python3 app/smoke.py — starts its own copy, hits /health + one /inspect
```

```sh
.venv/bin/python tools/run_demo.py  # the demo above, end to end
.venv/bin/python -m eval.run_eval   # regenerates docs/evaluation.md from the committed set
```

There is no `make` target for either; the report the second one writes is
[`docs/evaluation.md`](./docs/evaluation.md).

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

## HTTP API (`app/server.py`)

`make run` (or `python3 app/server.py`) serves the same `AgentLoop` over HTTP with the
standard library's `http.server` — no framework, since the runtime dependency set is exactly
OpenCV and numpy. One process, one in-memory loop; state does not survive a restart (there is
no persisted store).

| Route | What |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `POST /inspect` | body: raw image bytes. Runs `process_capture` (inspect -> decide -> the next call the verdict picks) and returns the capture's `state`, `measurements` and `verdict`. A body over 4 MB is rejected with `413 {"error": "payload_too_large"}` rather than a truncated decode. |
| `GET /trace/<capture_id>` | the capture's full ordered trace (a list of `TraceEntry` rows — see [The trace](#the-trace)) |
| `GET /pending` | captures currently `state == "escalated"`, waiting for a reviewer |
| `POST /approve/<capture_id>` | body: optional JSON `{"note": str}`. Calls `invoke("approve", ..., actor="reviewer")` — **the same call the agent's own tools would make with `actor="agent"`** for a tool they're refused; there is no second path to `"accepted"`. |
| `GET /`, `GET /review` | the approval page (`app/static/review.html`) — its Approve button `fetch()`s the same `POST /approve/<capture_id>` above |

```sh
make run &
curl -s http://127.0.0.1:8080/health
curl -s -X POST --data-binary @data/synthetic/not_doc.jpg \
  -H 'Content-Type: image/jpeg' http://127.0.0.1:8080/inspect
# open http://127.0.0.1:8080/ in a browser to approve the resulting escalation
```

## Layout

```
src/secondlook/
  schema.py       Measurements / Verdict / RuleFiring / TraceEntry — the structured results
  metrics.py      one pure function per measurement
  perception.py   inspect(): rectify first, then the other seven, timed
  policy.py       decide(): the cascade, first match wins, every clause recorded
  policy.toml     the committed threshold table and perception parameters
  agent_loop.py   invoke(tool, args, actor) chokepoint + process_capture loop driver
app/
  server.py       the local HTTP serving layer
  smoke.py        the smoke command: starts its own server, hits /health + one /inspect
  static/review.html   the approval page; its button calls the same invoke() the tools call
deploy/
  handler.py      the Lambda Function URL entry point, same chokepoint as server.py
  Dockerfile      arm64 container image on public.ecr.aws/lambda/python:3.13
  build.sh        local image build — no AWS credential needed
  deploy.sh       ECR push + function create/update + Function URL (owner-run only)
  smoke_local.py  runs the built image's handler against a committed sample
  iam-policy.json the permissions deploy.sh needs
eval/run_eval.py        the evaluation harness; writes docs/evaluation.md
docs/                   report.md, submission.md, architecture.md + .mmd + .svg,
                        agent-workflow.md + .mmd + .svg, evaluation.md, deploy.md,
                        video-script.md
tools/make_samples.py   the synthetic-set generator (seed 20260908)
tools/run_demo.py       runs the demo end to end, prints the trace
data/synthetic/         17 samples + manifest.json ground truth + LICENSE (MIT)
models/README.md        no weights vendored; the classical text path is the default
tests/                  test_metrics, test_policy, test_schema, test_samples, test_opencv_version,
                        test_agent_loop, test_handler, test_deploy_handler
```

## Deployment

The target is one AWS Lambda function, packaged as a **container image** on **arm64
(Graviton2)**, 2048 MB, Python 3.13, behind a **Lambda Function URL** — no load balancer, no API
Gateway, nothing billing while idle. 2048 MB is above the 1,769 MB point where Lambda allocates
a full vCPU, and this pipeline is CPU-bound. Lambda's synchronous payload cap is 6 MB, so both
entry points reject a body over 4 MB with `413 payload_too_large`.

Considered and rejected:

- **AWS App Runner** — "will no longer accept new customers starting on April 30, 2026"
  (<https://aws.amazon.com/apprunner/>). For an account that has never used it, it is
  unavailable, not merely inadvisable.
- **Amazon ECS Express Mode**, AWS's named App Runner replacement — it provisions an
  Application Load Balancer plus at least one always-running Fargate task, which bill
  continuously at zero traffic, and its documented continuous-deployment path is GitHub
  Actions; this repository uses no CI.
- **EC2, plain Fargate, SageMaker endpoints** — always-on compute for a workload that is idle
  between requests. **API Gateway** — a Function URL already gives HTTPS and public access.

`deploy/deploy.sh` is committed and idempotent, and no automation runs it. Creating the AWS
account and pushing the container image are owner actions. The runbook, with the build / smoke
/ deploy / verify steps and the rollback command, is [`docs/deploy.md`](./docs/deploy.md).

**Live endpoint: not deployed — blocked, not pending.** The only AWS account available for
this submission is a Free Plan "Project" whose Organization-level Service Control Policy
denies `ecr:CreateRepository` and `lambda:CreateFunction` outright, confirmed against the
real account on both the container path and a sized-and-verified `.zip` fallback. This is
an account-tier restriction, not a gap in this entry's code — the full attempt log with
real AWS error output is in [`docs/deploy.md`](./docs/deploy.md#deploying-second-look).

## What is not built

Stated here so nothing above reads as a claim it isn't:

- `apply.py` / `store.py` — S3-backed persistence. State is in memory, so a restart or a new
  Lambda execution environment starts with an empty batch.
- Structured CloudWatch logging, one line per trace entry.
- `overlay.py` — the annotated evidence image (quad, glare boxes, blur tiles, text boxes).
- `src/secondlook/handler.py` — `deploy/handler.py` is the working interim Lambda entry point.
- The browser *agent lane* (an `index.html` with a drop zone and a verdict panel). The review
  lane, `app/static/review.html`, is built.
- The `override`, `discard` and `close_batch` human verbs, and an HTTP route for
  `resolve_duplicate`.
- The DNN text detector (`dnn.TextDetectionModel_DB` over ONNX weights).
- A real-photograph evaluation set (`data/real/`).

## Documentation

| Document | What |
|---|---|
| [`docs/report.md`](./docs/report.md) | the technical report: problem, users, architecture, OpenCV 5 implementation, AWS deployment, evaluation, limitations, responsible use |
| [`docs/submission.md`](./docs/submission.md) | the Devpost write-up and the submission status |
| [`docs/architecture.md`](./docs/architecture.md) | architecture diagram ([`.svg`](./docs/architecture.svg), [`.mmd`](./docs/architecture.mmd)) — OpenCV 5 and AWS components, drawn as built |
| [`docs/agent-workflow.md`](./docs/agent-workflow.md) | agent workflow diagram ([`.svg`](./docs/agent-workflow.svg), [`.mmd`](./docs/agent-workflow.mmd)) — perception, decision, action, and the human lane |
| [`docs/evaluation.md`](./docs/evaluation.md) | generated evaluation report: task success, failure cases, limitations |
| [`docs/deploy.md`](./docs/deploy.md) | the deployment runbook (owner-run) |
| [`docs/video-script.md`](./docs/video-script.md) | the script and shot list the demo video was produced from |

## Licence

MIT — see [`LICENSE`](./LICENSE).

The sample data is synthetic and ours: `tools/make_samples.py` renders it from a fixed seed,
and it is MIT (`data/synthetic/LICENSE`). No real photographs and no model weights are
shipped. A real set, if one is added, will be owner-shot or
[CORD](https://github.com/clovaai/cord) under CC BY 4.0 with attribution.
