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

Read [`SPEC.md`](./SPEC.md) for the customer problem, the eight OpenCV 5 measurements and
what changed from 4.x, the tool contracts, the data model and trace schema, the demo script,
the decision layer, the AWS target, the evaluation plan, and the hackathon submission
checklist.

**Status:** code-complete and tested; deploying is the remaining owner action.

| Layer | State |
|---|---|
| `inspect()` (eight OpenCV 5 measurements) + `decide()` (rule cascade) | Built, tested against a synthetic set with exact ground truth |
| `agent_loop.py` — SPEC § 5 agent tools and human verbs behind one `invoke(tool, args, actor)` chokepoint | Built: `process_capture` lets the OpenCV verdict pick the next tool call, a human-approval wait resumes only on a real `invoke()` call, and the trace reconstructs SPEC § 7's demo table from real per-capture data (`python tools/run_demo.py` runs it end to end) |
| `app/server.py` — local HTTP serving (`make run`) | Built: the approval page's Approve button calls the exact same `invoke("approve", ...)` the tools call; `app/smoke.py` (`make smoke`) exercises it end to end |
| `deploy/handler.py`, the container image, [`docs/deploy.md`](./docs/deploy.md) | Built |
| [`docs/evaluation.md`](./docs/evaluation.md) | Built |
| Live AWS deploy | **Blocked, not pending** — the only available AWS account's own Service Control Policy denies both `ecr:CreateRepository` and `lambda:CreateFunction`; see `docs/deploy.md` |
| `apply.py`/`store.py` (persistence), `overlay.py` (evidence image) | Not built — see `SPEC.md` [§ 12](./SPEC.md#12-file-layout) |

Both serving paths (`app/server.py` and `deploy/handler.py`) are in-memory, matching
`agent_loop.py`'s own scope, until `store.py` lands.

## Stack (pinned in `SPEC.md` § 11)

- Python 3.13 on `public.ecr.aws/lambda/python:3.13` (arm64 / Graviton2)
- `opencv-python-headless==5.0.0.93` — OpenCV 5.0.0; the pin is exact because
  `opencv-python` 4.14.x also exists and a loose constraint resolves backwards into the 4.x
  line, where the warping numerics differ
- `numpy==2.5.3`
- `pytest==9.1.1`, `ruff==0.16.6`, `Pillow==12.3.0` (dev only; Pillow is not in the Lambda
  image)
- One static HTML page, vanilla JavaScript — no framework, no bundler
- AWS Lambda container image behind a Lambda Function URL, with one private S3 bucket and
  CloudWatch Logs. **Not AWS App Runner**, which
  [closed to new customers on 30 April 2026](https://aws.amazon.com/apprunner/) — see
  `SPEC.md` [§ 9](./SPEC.md#9-serving-surface-and-aws-target) for why ECS Express Mode was
  also considered and rejected.

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
cd entries/opencv
make setup     # python3.13 -m venv .venv && pip install --require-hashes -r requirements-dev.lock
make test      # pytest — metrics, policy, schema, samples, OpenCV version
make lint      # ruff check . && ruff format --check .
make samples   # regenerate data/synthetic/ from the fixed seed
bash verify.sh # the single gate the repo root's bin/verify.sh calls: doc checks + lint + tests
```

```sh
make run      # python3 app/server.py — binds 127.0.0.1:8080 (PORT env var overrides)
make smoke    # python3 app/smoke.py — starts its own copy, hits /health + one /inspect
```

```sh
.venv/bin/python -m eval.run_eval   # regenerates docs/evaluation.md from the committed set
```

There is no `make` target for it; the report it writes is
[`docs/evaluation.md`](./docs/evaluation.md).

Using the pipeline from Python:

```python
from secondlook import decide, inspect_file, load_policy

policy = load_policy()  # src/secondlook/policy.toml
record = inspect_file("data/synthetic/glare_text.jpg")  # Measurements — SPEC § 6
verdict = decide(record, policy)  # Verdict — SPEC § 6
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
standard library's `http.server` — no framework, matching SPEC § 11's stack pin, which
names none for the runtime. One process, one in-memory loop; state does not survive a
restart (that's `store.py`'s job, still a follow-up goal).

| Route | What |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `POST /inspect` | body: raw image bytes. Runs `process_capture` (inspect -> decide -> the next call the verdict picks) and returns the capture's `state`, `measurements` and `verdict`. A body over 4 MB is rejected with `413 {"error": "payload_too_large"}` rather than a truncated decode. |
| `GET /trace/<capture_id>` | the capture's full ordered trace (SPEC § 6 `TraceEntry` list) |
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
  metrics.py      one pure function per measurement (SPEC § 4)
  perception.py   inspect(): rectify first, then the other seven, timed
  policy.py       decide(): the cascade, first match wins, every clause recorded
  policy.toml     the committed threshold table and perception parameters
  agent_loop.py   invoke(tool, args, actor) chokepoint + process_capture loop driver (SPEC § 3, § 5, § 7)
app/
  server.py       the local HTTP serving layer
  smoke.py        the smoke command: starts its own server, hits /health + one /inspect
  static/review.html   the approval page; its button calls the same invoke() the tools call
deploy/
  handler.py      the Lambda Function URL entry point (SPEC § 9), same chokepoint as server.py
  Dockerfile      arm64 container image on public.ecr.aws/lambda/python:3.13, digest-pinned
  build.sh        local image build — no AWS credential needed
  deploy.sh       ECR push + function create/update + Function URL (owner-run only, #47)
  smoke_local.py  runs the built image's handler against a committed sample
  iam-policy.json the permissions deploy.sh needs
eval/run_eval.py        the evaluation harness; writes docs/evaluation.md
docs/                   report.md, submission.md, architecture.md + .mmd + .svg,
                        agent-workflow.md + .mmd + .svg, evaluation.md, deploy.md
tools/make_samples.py   the synthetic-set generator (seed 20260908)
tools/run_demo.py       runs SPEC § 7's demo script end to end, prints the trace
data/synthetic/         17 samples + manifest.json ground truth + LICENSE (MIT)
models/README.md        no weights vendored; the classical text path is the default
tests/                  test_metrics, test_policy, test_schema, test_samples, test_opencv_version,
                        test_agent_loop, test_handler
```

## Deployment

`deploy/deploy.sh` is committed and idempotent, and **no goal runs it**. Creating the AWS
account, pushing the container image, and submitting on Devpost are owner actions — see
`CLAUDE.md` at the repo root. The runbook, with the build / smoke / deploy / verify steps and
the rollback command, is [`docs/deploy.md`](./docs/deploy.md).

**Live endpoint: not deployed — blocked, not pending.** The only AWS account available for
this submission is a Free Plan "Project" whose Organization-level Service Control Policy
denies `ecr:CreateRepository` and `lambda:CreateFunction` outright, confirmed against the
real account on both the container path and a sized-and-verified `.zip` fallback. This is
an account-tier restriction, not a gap in this entry's code — the full attempt log with
real AWS error output is in [`docs/deploy.md`](./docs/deploy.md#deploying-second-look).

## Documentation

| Document | What |
|---|---|
| [`docs/report.md`](./docs/report.md) | the technical report: problem, users, architecture, OpenCV 5 implementation, AWS deployment, evaluation, limitations, responsible use |
| [`docs/submission.md`](./docs/submission.md) | the Devpost write-up and the owner's submission checklist |
| [`docs/architecture.md`](./docs/architecture.md) | architecture diagram ([`.svg`](./docs/architecture.svg), [`.mmd`](./docs/architecture.mmd)) — OpenCV 5 and AWS components, drawn as built |
| [`docs/agent-workflow.md`](./docs/agent-workflow.md) | agent workflow diagram ([`.svg`](./docs/agent-workflow.svg), [`.mmd`](./docs/agent-workflow.mmd)) — perception, decision, action, and the human lane |
| [`docs/evaluation.md`](./docs/evaluation.md) | generated evaluation report: task success, failure cases, limitations |
| [`docs/deploy.md`](./docs/deploy.md) | the deployment runbook (owner-run) |

## Licence

MIT — see [`LICENSE`](./LICENSE).

Sample data licences are recorded in `SPEC.md` § 10: the primary set is synthetic and ours
(`data/synthetic/LICENSE`, MIT); real photographs come from
[CORD](https://github.com/clovaai/cord) under CC BY 4.0 with attribution, or from the
owner's own camera.
