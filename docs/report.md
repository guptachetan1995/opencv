# Second Look — technical report

Submitted to the [OpenCV AI Competition 2026, powered by AWS](https://opencv26.devpost.com/),
on the **Agentic Vision** path.

The competition asks for "a technical report describing the problem, users, architecture,
OpenCV 5 implementation, AWS deployment, evaluation, limitations, and responsible-use
considerations." The eight sections below are in that order, so each requirement can be
checked against one heading.

Companion documents: [`architecture.md`](./architecture.md) and
[`architecture.svg`](./architecture.svg), [`agent-workflow.md`](./agent-workflow.md) and
[`agent-workflow.svg`](./agent-workflow.svg), [`evaluation.md`](./evaluation.md) (every
number quoted here), [`deploy.md`](./deploy.md) (the deployment runbook), and
[`submission.md`](./submission.md).

**Live endpoint:** none yet. The Lambda deployment was attempted and is **blocked**: the
only AWS account available for this submission denies `ecr:CreateRepository` and
`lambda:CreateFunction` via an Organization-level Service Control Policy tied to its Free Plan
tier. An EC2 console deploy of the same routes is prepared for the owner to launch. See § 5,
and [`deploy.md`](./deploy.md) for the real error output and every console field. Until an
endpoint serves, a live screen-share of the running local server is available to judges on
request via a Devpost message.

---

## 1. Problem

Take a nine-person surveying and site-inspection firm — an illustrative case, not a customer
this entry has worked with. Everyone is out of the office most days and everyone pays for
things — fuel, parking, materials, a replacement cable from a hardware shop. The policy is
ordinary: photograph the receipt, and finance sorts it out at month end.

Month end is where the money goes. Somewhere between four and thirty days after the shutter,
a bookkeeper opens a capture and finds a white bar of window glare lying exactly across the
total; or the bottom third out of focus because the phone focused on the table; or the tax
line cropped off at the frame edge; or the same receipt photographed twice. By then the
surveyor is on another site in another county and the paper is in a bin. The claim is
dropped, guessed at, or bounced back to someone who cannot fix it, because the evidence no
longer exists.

The usual diagnosis is that this is an OCR problem, so firms buy an OCR product. That misses
where the cost comes from. Capture-time checks exist — scanner SDKs grade blur and text
readability, and expense apps let a user retake a scan that failed (README, "What already
exists") — but a capture that passes them, or a failure noticed only when the claim is
processed, still reaches the bookkeeper as an unusable image. **The expensive quantity is
the latency between a bad capture and anyone knowing it was bad**, because that latency is
what makes the defect permanent. Two seconds after the shutter, standing in the same light,
the surveyor can just take the photo again. Three weeks later, nobody can.

There is a second, subtler trap. A tool that decides "good enough" on its own is wrong in two
directions, and the two errors do not cost the same. Nagging someone for a retake they did
not need costs a few seconds of irritation. Silently accepting an unreadable capture costs
the whole claim, and the person who pays is not the person who made the error. That
asymmetry is why this entry's headline evaluation metric is the **silent-accept rate** and
not overall accuracy, and why every genuinely ambiguous capture is routed to a human while
the evidence still exists.

## 2. Users

- **The person holding the phone** (a surveyor, in the field, in bad light, in a hurry).
  They get one of three answers within seconds of the shutter: it is fine; take it again and
  here is the one thing to fix and where; or a person will look at this. They never see a
  metric name, only the instruction and the region.
- **The bookkeeper / reviewer.** They get a queue that contains only what genuinely needs a
  human — the uncertain band, a defect that survived two retakes, a suspected duplicate,
  anything that does not look like a document — and each item carries the measurement that
  put it there. They are the only party who can accept a borderline capture, resolve a
  duplicate, or overturn a verdict.
- **The competition judge**, as a third user in practice: the same review page, the same
  chokepoint, plus a committed trace they can read to see which measurement caused which
  call.

## 3. Architecture

Diagram: [`architecture.svg`](./architecture.svg), with the Mermaid source and a full
walkthrough in [`architecture.md`](./architecture.md).

The path of one capture:

```
client (browser)
  → app/server.py (local, make run)  |  deploy/handler.py (AWS Lambda Function URL)
      → agent_loop.process_capture
          → agent_loop.invoke("inspect_capture", …, actor="agent")  → perception.inspect()  [OpenCV 5]
          → agent_loop.invoke("decide_capture",  …, actor="agent")  → policy.decide()       [11-rule cascade]
              → accept   → _mark_accepted → loop.accepted_hashes
              → retake   → invoke("request_recapture", {failing_metric, hint_box}, actor="agent")
              → escalate → invoke("escalate", {reason}, actor="agent") → the human review lane
```

Three entry points, one loop. The HTTP routes are written once, in
`src/secondlook/service.py`; `app/server.py` (stdlib `ThreadingHTTPServer`, no framework — `make
run` and the EC2 image) and `deploy/handler.py` (Lambda Function URL, payload format 2.0) are
thin adapters that translate their request shape into one `Service.handle(...)` call. The
routes hold no decision logic: each is a `process_capture` or `invoke(...)` call. Both HTTP
adapters enforce the same `MAX_BODY_BYTES = 4 MB` guard, under Lambda's 6 MB synchronous payload
cap, and reject an oversized body with `413 payload_too_large`. The third entry point,
`app/mcp_server.py`, is a stdio MCP server that offers the agent tools (never the human verbs)
to an LLM agent, each as the same `invoke(..., actor="agent")` call. Its two photo-arrival
tools, `open_capture` and `attach_retake`, decide nothing and use the same ungated plumbing as
`POST /inspect` and `POST /retake` (`AgentLoop.open_capture`, `AgentLoop.attach_image`).

### The chokepoint, and why it is checkable rather than merely documented

Every agent tool call, every human verb, and the review page's Approve button enter the
system through one function, `agent_loop.invoke(tool, args, actor)`. Its first act is the
actor guard (`src/secondlook/agent_loop.py`):

```python
if tool in HUMAN_VERBS and actor != "reviewer":
    raise PermissionError(f"{tool!r} is human-only; actor was {actor!r}")
if tool in AGENT_TOOLS and actor != "agent":
    raise PermissionError(f"{tool!r} is an agent tool; actor was {actor!r}")
```

`HUMAN_VERBS` is `("approve", "reject", "resolve_duplicate")`; `AGENT_TOOLS` is
`("inspect_capture", "decide_capture", "request_recapture", "compare_captures", "escalate")`.
The agent has no private path to the accepted state and the human has no private path to the
agent's tools — and because both land on the same function, the separation is a property the
test suite can assert rather than a convention a later change can quietly erode.

The actor guard alone is not enough, and an earlier version of this entry showed why: an agent
could call `decide_capture` on an escalated capture, move it back to `measured`, request a
retake of it, and have the retake auto-accept — out of the review queue with no person
involved. So every agent tool also checks the capture's state and raises `StateError` unless
it is `received` or `measured`; `request_recapture` additionally needs the capture's own
verdict to be `retake`; and `get_capture` returns a fresh dict, never the live record.
`tests/test_agent_loop.py` replays that exact sequence and asserts each agent tool is refused
and the capture stays `escalated`.
`open_capture()` and `attach_image()` are deliberately *ungated* plumbing: they create a slot
and put bytes in it, and mutate nothing a verdict depends on except the retake `attempt`
counter, which they derive from `parent_id` rather than accept as caller-supplied input.
`attach_image()` refuses anything but an open, unmeasured retake slot.

The review page proves the point at runtime: `app/static/review.html`'s Approve, Reject and
duplicate buttons `fetch()` `POST /approve/:id`, `/reject/:id` and `/resolve_duplicate/:id`,
and each route is a call to `invoke(verb, …, actor="reviewer")` — the identical function the
agent's own tools call, refused to the agent by the guard above. Over HTTP the reviewer is also
authenticated: those routes, and the photo overlay, need `Authorization: Bearer <reviewer
token>` and answer `401` before any `invoke()` without it. The page shows each escalated
capture's evidence overlay, the clause that fired and its key measurements, so the person
deciding sees what the agent saw.

**The diagrams are drawn as built, not as the design sketched them** before any code
existed: solid means built and exercised by tests, dashed means planned and not built, and
each dashed node names what it waits on.
[`architecture.md`](./architecture.md#where-this-diverges-from-the-pre-code-design) lists the
divergences (chief among them: the chokepoint is `agent_loop.invoke()`, not the separate
apply-module the design imagined; S3, CloudWatch, the DNN text path and the UI's agent lane are
unbuilt). Overstating what exists is a documented rejection ground for
this competition, so the corrections are recorded rather than smoothed over.

**No AWS COOL service is used by this entry**, so nothing COOL appears on the architecture
diagram; the requirement's "where relevant" clause is not relevant here, and saying so
explicitly is more useful to a judge than a silent omission.

## 4. OpenCV 5 implementation

Pin: **`opencv-python-headless==5.0.0.93`** (OpenCV 5.0.0), asserted by
`tests/test_opencv_version.py` and by `verify.sh`. The pin is **exact**, not a range, because
`opencv-python` 4.14.x also exists on PyPI and a loose constraint resolves *backwards* into
the 4.x line, where the warping numerics differ — a silent 4.x resolution would change
rectification output and therefore change verdicts. `opencv-contrib-python-headless` is
deliberately not a dependency; every call below is core OpenCV. `metrics.dnn_engine_name()`
reports OpenCV 5's **`new`** DNN engine, and that string is recorded in every measurement
record's provenance.

`perception.inspect()` runs eight measurements and returns one frozen `Measurements` record
of 31 fields — numbers, flags, box coordinates and provenance. Rectification runs *first* and
every later measurement reads the rectified page, which is why blur and glare are reported by
location on the receipt rather than as one score for the photograph.

| # | Measurement | OpenCV 5 calls (`src/secondlook/metrics.py`) |
|---|---|---|
| 1 | Document quad + rectification | `cvtColor`, `GaussianBlur`, `Canny`, `dilate`, `findContours`, `approxPolyDP`, `isContourConvex`, `contourArea`, `pointPolygonTest`, with a `HoughLinesP` line-intersection fallback; then `getPerspectiveTransform` + `warpPerspective` |
| 2 | Focus, per tile | `Laplacian` (CV_64F) variance over a 6×8 grid of the rectified page, normalised per unit ink |
| 3 | Exposure and contrast | `calcHist` → `clipped_low_frac`, `clipped_high_frac`, `contrast_p95_p5` |
| 4 | Specular glare | `cvtColor` BGR→HSV, low-saturation/high-value threshold, `morphologyEx` OPEN then CLOSE, `connectedComponentsWithStats`; `glare_over_text_frac` intersects glare with the text mask |
| 5 | Text presence and coverage | **classical** black-hat morphology: `getStructuringElement` + `morphologyEx` MORPH_CLOSE + `subtract` for the ink map, then `morphologyEx` + `connectedComponentsWithStats` for line boxes |
| 6 | Frame-edge crop | the located quad against the frame border margin → `edge_touch_sides`, plus `bottom_band_has_text` |
| 7 | QR / barcode | `QRCodeDetector().detectAndDecode`, then `barcode_BarcodeDetector().detectAndDecode` |
| 8 | Duplicate | dHash via `resize` to 9×8 + row-gradient bits, Hamming distance against the batch's accepted hashes |

Two honest notes about measurement 5. **The DNN text path is not built.**
`perception.TEXT_DETECTOR` is the literal string `"classical"`, `models/README.md` vendors no
weights, and every `Measurements` record carries `text_detector` so any report states which
path produced it. The pre-code design wanted `dnn.TextDetectionModel_DB` on the diagram; it is
drawn dashed as the unbuilt alternative instead of being claimed.

The same measurements are drawn back onto the image by `src/secondlook/overlay.py`, with OpenCV
drawing calls: the frame with the located quad, and the page re-warped from the stored quad onto
exactly `page_shape` with the text boxes, blur tiles, glare boxes and the verdict's hint box,
under the clause that fired. It is rendered per request for the reviewer, never stored.

But the OpenCV output is not a display artefact — it is the input to the next decision.
`glare_over_text_frac` (not `glare_area_fraction`) is what separates "glare on white space,
accept" from "glare across the total, retake"; `code_decoded` is a *clause* of the
`out_of_focus` rule, so a decoded QR cancels a retake a soft-focus page would otherwise get.
See [`agent-workflow.md`](./agent-workflow.md#the-qualifying-beat).

## 5. AWS deployment

**Surface:** one AWS Lambda function, packaged as a **container image**, on **arm64
(Graviton2)**, 2048 MB, Python 3.13, behind a **Lambda Function URL**. No Application Load
Balancer, no API Gateway. The base image is `public.ecr.aws/lambda/python:3.13`
(`deploy/Dockerfile`); the image is pushed to **Amazon ECR** and the function points at the
tag. Memory is set above the 1,769 MB point where Lambda allocates a full vCPU, because this
pipeline is CPU-bound.

**AWS App Runner is ruled out and must not be reintroduced:** it "will no longer accept new
customers starting on April 30, 2026", verbatim from <https://aws.amazon.com/apprunner/>. This
entry would be standing up a brand-new service in an account that has never used App Runner,
so it is unavailable rather than merely inadvisable. Amazon ECS Express Mode was considered
and rejected: its documented path provisions an Application Load Balancer plus at least one
always-running Fargate task, which bills continuously at zero traffic through the whole
judging window, and its documented continuous-deployment path is GitHub Actions, which this
repository forbids. Lambda bills nothing while idle, and its free tier — "one million
requests and 400,000 GB-seconds per month", per <https://aws.amazon.com/lambda/pricing/> —
covers a demo, an evaluation run and a judging window.

**Four steps for Lambda**, with the exact commands in [`deploy.md`](./deploy.md):

1. **Build** — `deploy/build.sh` (`docker build --platform linux/arm64`). Local, no AWS
   credential needed.
2. **Local smoke** — `deploy/smoke_local.py` calls `handler.handler()` in-process
   (Docker-free, AWS-free) against a committed sample before anything is pushed.
3. **Push and deploy** — `deploy/deploy.sh`: create/reuse the ECR repository, push the tagged
   image, create or update the function (`--architectures arm64`), create the Function URL.
   Idempotent; every setting is read as `${VAR:-default}`, nothing is hard-coded.
4. **Verify** — hit `/health` and `POST /inspect` against the Function URL.

**Rollback** is repointing the function at the previous ECR tag, which stays in the registry
until pruned:

```sh
aws lambda update-function-code --function-name "$FUNCTION_NAME" \
  --image-uri "$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:PREVIOUS_TAG"
```

**Deploying is an owner-only action, and it was attempted — twice — and blocked.**
No automation in this repository runs `deploy.sh`; the owner ran it personally on 2026-09-17
against the only AWS account available for this submission. `ecr:CreateRepository` was
denied by an explicit Service Control Policy on that account's AWS Organization. A second
attempt ruled out "it's specific to container images": a Lambda `.zip` package was sized
against the real pinned dependencies (140 MB unpacked, comfortably under Lambda's 250 MB
ceiling), but `lambda:CreateFunction` was denied by the identical policy regardless of
packaging format. Both real errors are captured verbatim in
[`deploy.md`](./deploy.md#deploying-second-look).

The account is a "Project" under AWS's Free Plan (Builder ID) product — a curated,
guardrailed tier whose Organization-level policy the account holder cannot see or edit
from inside the account itself. Lifting it requires either AWS's irreversible "activate
advanced features" step (which itself needs a paid upgrade first, and would restructure
the whole organization, which also hosts another project's live deployment) or a separate,
unrestricted AWS account. Neither was available: no spare email for a new account, no
budget for the upgrade. Rather than paper over this, it's reported here plainly — the
same standard this report holds every other limitation to. `deploy.sh`, `deploy/handler.py`
and the container image are all built, tested locally, and ready to run unmodified the
moment an unrestricted account exists. Both attempts were in `us-east-1`.

**The EC2 path, prepared for the owner to launch.** Another project in the same AWS
organization was deployed to EC2 through the console on 2026-09-11 in `ap-southeast-2`, so the
same route table is prepared as one `t3.micro` there: `deploy/ec2/Dockerfile` (`app/server.py`
on `python:3.13-slim`), built on first boot by `deploy/ec2/user-data.sh` from the public
repository and served on port 80, with a reviewer token generated on the instance and never
written into the form or the repository. [`deploy.md`](./deploy.md#ec2-console-deploy) lists
every console field; the owner reviews them and clicks Launch, and the verification output goes
into `deploy.md` when it exists. It has not been launched at the time of writing.

## 6. Evaluation

Full report with every table: [`evaluation.md`](./evaluation.md). It is generated output, not
a hand-typed table — every number comes from a real run through the same `invoke()`
chokepoint the demo and the test suite use.

Reproduce it with:

```sh
# from the repository root
make setup
.venv/bin/python -m eval.run_eval
```

Set **S** is the committed synthetic set: `data/synthetic/manifest.json`, seed **20260908**,
**17 samples** with exact ground truth by construction; 15 of the 17 carry an
`expected_verdict` (the other two exist only for a monotonic-focus assertion in
`tests/test_metrics.py`). Measured on `opencv-python-headless 5.0.0`, DNN engine `new`,
classical text detector.

| Metric | Value |
|---|---|
| Task-success rate | **15/15 (100.0%)** — `(outcome, rule_id)` matches the manifest per sample |
| **Silent-accept rate** | **0/15 (0.0%)** — the headline number: no accepted capture, auto or reviewed, disagrees with ground truth |
| Accept rate | 6/17 (35.3%) |
| Retake rate | 7/17 (41.2%) |
| Escalate rate | 4/17 (23.5%) |
| Escalation precision | 4/4 (100.0%) — **with the caveat below** |
| Retake convergence | **5/6 (83.3%)** — sequences reaching `accept` within two retakes |
| Task success, **shared batch** | **9/15 (60.0%)** — the same samples through one batch in manifest order |
| Silent-accept rate, shared batch | **0/15 (0.0%)** |
| Approval latency (simulated) | a little over the harness's scripted 50 ms pause, and it moves from run to run — **not a human number**; see below |

Per-defect detection is **100.0%** on all eleven classes present in the set: `blur_global`
(n=2), `blur_partial` (1), `crop` (1), `duplicate` (1), `exposure` (2), `faded` (1), `glare`
(2), `none` (2), `not_a_document` (1), `perspective` (1), `two_documents` (1).

Tool-call and human-verb counts over the isolated pass of all 17 samples: `inspect_capture`
17, `decide_capture` 17, `request_recapture` 7, `escalate` 4, `reject` 3, `resolve_duplicate`
1. The counts are the loop's own behaviour, read from the traces.

The isolated numbers are how the ground truth was written: one receipt, one batch. Through one
shared batch, 6 of the 15 samples collide as suspected duplicates of an already-accepted
receipt with the same printed layout — `glare_text.jpg` posted after `clean_a.jpg` escalates
instead of asking for a retake — so task success drops to 9/15 while the silent-accept rate
stays 0/15: every collision goes to a person (Failure Case 1 below).

Two numbers must be read with their caveats, and the report states both rather than quoting
the round figures alone. **Approval latency is simulated**: this harness has no human in it,
so the figure is the wall-clock between a scripted `time.sleep` and the next `invoke()` call.
It demonstrates that the trace's timestamps are sufficient to *compute* real approval latency
once a real reviewer exists, and says nothing about how long a person takes. **Escalation
precision is trivially 100%** because every escalated fixture in set S is a genuinely bad or
ambiguous capture by construction; a fixture where the correct human call is to *overturn* an
escalation needs the real-photograph set, which does not exist yet.

The **retake-convergence sequence set** is where the agentic claim is measured rather than
asserted. Six scripted sequences; five converge, and the sixth correctly does not:
`glare_text → crop_bottom → clean_a` converges in 2 retakes with the second retake fired by a
*different rule from a different metric*, while `blur_4 → blur_4 → blur_4` escalates as
`persistent_defect` on the third decision instead of asking a third time.

> **Headline numbers, before the limitations below qualify them:** task success **15/15
> (100.0%)** on set S, and the metric this entry is built around — **silent-accept rate
> 0/15 (0.0%)** — no accepted capture, auto or reviewed, ever disagreed with ground truth.

## 7. Limitations

Four named failure cases, from [`evaluation.md`](./evaluation.md), measured rather than
guessed:

1. **Batch-level duplicate collision across a shared template (limitation).** Running the
   whole manifest through one shared batch produces 6 captures that escalate as
   `suspected_duplicate` against the manifest's own expectation. dHash runs on the
   *rectified* page, so every defect variant of the same synthetic layout rectifies close
   enough to an already-accepted capture to fall at or under the Hamming threshold of 6 —
   `warp.jpg` against `clean_b.jpg` is an exact match at distance 0 despite the keystone. In
   the field, a batch of receipts from one vendor on one printed template risks false
   `suspected_duplicate` escalations driven by template similarity rather than content. It
   never produces a silent accept — escalation is the safe direction — but it sends work to a
   human who did not need it.
2. **One `reason_code` covers two different causes (limitation).** `not_a_document` fires on
   `quad_found == false` OR on `text_coverage_fraction` under the floor. `not_doc.jpg` matches
   the first clause and `faded.jpg` the second, yet both surface the identical reason code, so
   a reviewer reading only the code cannot tell "there is no page here" from "there is a real
   but very faded receipt here" — two different corrective actions. The distinguishing
   evidence is in the trace's `firings`; the reason code alone does not carry it.
3. **No verb yet resolves `two_documents` correctly (limitation).** The designed fix is a
   person picking the right receipt, which needs `override` or `discard` — human-only verbs
   that are specified but not built. The reviewer can only `reject` the whole capture: safe,
   but it discards a possibly-fine receipt along with the bad one.
4. **The agent stops guessing after two retakes (handled).** `blur_4 → blur_4 → blur_4`
   reaches `escalate` / `persistent_defect` on the third decision rather than requesting a
   third retake. Included because "did not converge" is the correct answer here, not a defect.

Five limitations of the evaluation itself:

- **No real-photograph set.** Every number is set S (synthetic). Verdict agreement against
  hand labels, and a case where a reviewer genuinely disagrees with an escalation, both need
  a real set and are not measured. The collection protocol is
  [`real-photo-set.md`](./real-photo-set.md), and the harness scores set R as soon as
  `data/real/manifest.json` exists.
- **Approval latency is simulated,** not measured against a real reviewer.
- **Latency and cost against a deployed endpoint are unmeasured.** The evaluation runs the
  in-memory loop locally; the Lambda path is blocked by the account restriction in § 5, and
  the EC2 path has not been launched.
- **The retake-convergence set is scripted, not sampled.** Six sequences chosen to exercise
  every retake-triggering rule plus the persistent-defect stop — not a random sample of real
  retake behaviour, because no real capture stream exists yet.
- **Escalation precision is trivially high (100%)** for the reason given in § 6.

And one capability limit that no number covers: **a photograph of a screen displaying a
receipt (moiré) is not detected.** It passes focus, glare and text coverage. No mitigation is
claimed. It is written up here because misrepresenting what the system catches is itself a
rejection ground for this competition.

Finally, scope: state is in memory. `store.py` (S3) and CloudWatch wiring are specified and
unbuilt, so a Lambda cold start loses the batch, and concurrent executions do not share it.
`src/secondlook/handler.py` is likewise unbuilt — `deploy/handler.py` is the working interim
entry point.

## 8. Responsible use

Receipts carry names, card last-four digits, addresses and locations, so:

- **No pixel data and no decoded text is ever stored in a record.** `Measurements` and
  `Verdict` are frozen dataclasses of numbers, flags, box coordinates and rule identifiers. A
  QR payload is dropped inside the metric that read it; only the boolean `code_decoded`
  survives. This is a schema-level guarantee (`src/secondlook/schema.py`, asserted by
  `tests/test_schema.py`), not a logging convention.
- **The photo itself is kept only while a person needs to see it.** An upload is deleted as
  soon as the loop has read it, unless the capture escalated; then it is held in the server's
  temporary directory so the reviewer can see the overlay, and deleted the moment the reviewer
  decides (at most 64 held; the oldest is deleted first). The overlay is drawn per request and
  needs the reviewer token.
- **Nothing is ever sent anywhere.** No email, no accounting integration, no payment, no
  third-party API. The pipeline has no network call in it at all.
- **The irreversible decisions are human-only, and the guard in § 3 enforces it** — not by
  documentation but by a `PermissionError` at the one function every call must pass through.
  An escalated capture stops moving until a person acts; there is no timer that eventually
  auto-approves.
- **This system judges capture quality, not the truthfulness of a claim.** It makes no
  assessment of a person. It does not read the receipt's contents, identify a merchant, or
  score anyone's behaviour.
- **Data licences are recorded**: the primary set is synthetic and ours
  (`data/synthetic/LICENSE`, MIT); no real photographs are shipped, and any added later would
  be owner-shot or CORD under CC BY 4.0 with attribution. No model weights are vendored
  (`models/README.md`). The entry itself is MIT ([`LICENSE`](../LICENSE)).
- **Known-undetected cases are reported as undetected** — the moiré case above is the
  example — because overstating capability is a stated rejection ground.

One deliberate, documented tradeoff: a public endpoint — the Function URL is created with
**`--auth-type NONE`**, and the EC2 instance serves plain HTTP — so a judge can reach it
without an AWS credential. That no longer exposes the human gate: approve, reject,
resolve-duplicate and the photo overlay need the reviewer token (`REVIEWER_TOKEN`), and answer
`401` without it. What stays public is posting a photo and reading measurements and traces.
Over plain HTTP the token protects those routes from casual callers, not from someone
observing the network; a production deployment would add TLS and real identity (IAM auth, or
a sign-in in front of the review page), and the planned S3 store assumes a private bucket with
Block Public Access on.

---

## Appendix — where each judging criterion is answered

For the six general criteria:

| Criterion | Weight | Where |
|---|---|---|
| Technical execution | 30% | § 3 (architecture and the chokepoint guard), § 4 (OpenCV 5 depth), § 6 (evaluation) |
| Innovation | 20% | § 1's framing (latency-to-knowing, not recognition accuracy) and § 4's use of `glare_over_text_frac` and `code_decoded` as *decision* inputs |
| Real-world impact | 20% | § 1 and § 2 — the cost asymmetry that makes silent accepts the expensive error |
| User experience | 10% | § 2, plus `app/static/review.html` (the evidence overlay, the clause that fired, Approve / Reject / resolve-duplicate) and the per-capture instruction with a hint box; the README's hero image |
| Documentation and presentation | 10% | this report, [`README.md`](../README.md), both diagrams, [`deploy.md`](./deploy.md) — and the demo video, <https://youtu.be/zOfV23uB8Ts>, scripted in [`video-script.md`](./video-script.md) |
| Cloud delivery, reproducibility, responsible operation | 10% | § 5 — the Lambda path is built, tested and **blocked** by the only available account's Free Plan guardrail (attempt log in [`deploy.md`](./deploy.md)); the EC2 console deploy is prepared for the owner to launch; rollback documented regardless; the hash-pinned locks; § 8 |

For the five Agentic Vision Award rubric lines:

| Rubric line | Weight | Where |
|---|---|---|
| Substantive OpenCV 5 and agent integration | 30% | § 4, and [`agent-workflow.md`](./agent-workflow.md) — measurements are the decision inputs, and the overlay draws them back onto the image; `app/mcp_server.py` offers the agent tools over MCP |
| Orchestration and appropriate autonomy | 25% | § 3 (the actor guard and the state guard), the 11-rule cascade, and `persistent_defect` stopping the loop after two retakes |
| Task effectiveness and evaluation | 20% | § 6 — 15/15 task success isolated and 9/15 in one shared batch, 0/15 silent accepts in both, 5/6 retake convergence |
| Failure handling, observability, security, human control | 15% | § 7 (four named failure cases), the trace (`GET /trace/:id`, `caused_by` chain), § 8 |
| User experience, documentation, and demonstration | 10% | § 2 and this report; the **demonstration** evidence is `tools/run_demo.py`'s printed trace, backed by the submission video, <https://youtu.be/zOfV23uB8Ts> |
