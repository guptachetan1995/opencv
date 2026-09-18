# Second Look — architecture

The diagram the OpenCV AI Competition rules ask for: "An architecture diagram showing the
OpenCV 5 and AWS components and, where relevant, COOL or agent components."

- Source: [`architecture.mmd`](./architecture.mmd) (Mermaid)
- Exported image: [`architecture.svg`](./architecture.svg)

**No AWS COOL service is used by this entry**, so nothing COOL appears on the diagram. The
agent components — the `invoke()` chokepoint, the loop driver, the human review lane — are
drawn in full, because they are the entry's whole claim.

## Legend

**Solid box or solid edge = built and exercised by tests. Dashed box or dashed edge =
planned, not built.** Every dashed node names the issue or the SPEC section it is deferred
to, so a reader can tell at a glance what runs today from what is on paper. The one heavily
outlined box, `agent_loop.invoke(tool, args, actor)`, is the single chokepoint: every arrow
from either entry point, from `process_capture`, and from the review page's Approve button
goes *into* it, and none route around it.

```mermaid
%% Second Look — architecture, drawn AS BUILT (not as SPEC § 16 sketched it).
%% Solid = built and exercised by tests. Dashed = planned, not built; each dashed node
%% names where it is deferred to. Source of truth: entries/opencv/src, app, deploy.
flowchart LR
  classDef built fill:#ffffff,stroke:#333333,stroke-width:1px,color:#111111
  classDef unbuilt fill:#f5f5f5,stroke:#999999,stroke-width:1px,stroke-dasharray: 6 4,color:#555555
  classDef choke fill:#fff3cd,stroke:#b8860b,stroke-width:3px,color:#111111
  classDef human fill:#e8f0fe,stroke:#3367d6,stroke-width:2px,color:#111111
  classDef note fill:#fafafa,stroke:#cccccc,stroke-width:1px,color:#444444

  subgraph CLIENT["Client"]
    PHONE["Phone or laptop browser"]
    REVIEW["app/static/review.html — the review lane<br/>Approve button fetches POST /approve/:capture_id"]
    AGENTLANE["index.html agent lane<br/>NOT BUILT — SPEC § 16A only"]
  end

  subgraph LOCAL["Local host — make run"]
    SERVER["app/server.py<br/>stdlib ThreadingHTTPServer, 127.0.0.1:8080<br/>MAX_BODY_BYTES = 4 MB"]
    SMOKE["app/smoke.py — make smoke"]
  end

  subgraph AWS["AWS"]
    FURL["Lambda Function URL<br/>HTTPS, public, auth-type NONE<br/>BLOCKED — account SCP denies lambda:CreateFunction"]
    LAMBDA["deploy/handler.py<br/>Lambda container image, payload format 2.0<br/>arm64 / Graviton2, 2048 MB, Python 3.13<br/>MAX_BODY_BYTES = 4 MB"]
    FUTUREH["src/secondlook/handler.py<br/>NOT BUILT — issue #90 —<br/>deploy/handler.py is the interim stand-in"]
    ECR["Amazon ECR<br/>public.ecr.aws/lambda/python:3.13 base, digest-pinned"]
    DEPLOYSH["deploy/build.sh + deploy/deploy.sh<br/>owner-run, no CI"]
    S3["Amazon S3 private bucket<br/>NOT BUILT — store.py, SPEC § 12"]
    CW["Amazon CloudWatch Logs<br/>NOT WIRED — SPEC § 9"]
  end

  subgraph CORE["Agent loop — one chokepoint for agent and human alike"]
    INVOKE["agent_loop.invoke(tool, args, actor)<br/>HUMAN_VERBS need actor=reviewer<br/>AGENT_TOOLS need actor=agent<br/>every mutation passes here or not at all"]
    PROC["agent_loop.process_capture<br/>perception → decision → action;<br/>a no-op once state == escalated"]
    PERC["perception.inspect() — the eight measurements, timed"]
    MEAS["Measurements — 31 frozen fields<br/>numbers, flags, boxes; no pixels, no decoded text"]
    POLICY["policy.decide() — 11-rule cascade, first match wins"]
    VERDICT["Verdict — outcome, rule_id, reason_code, hint_box, firings"]
    ACCEPT["accept → _mark_accepted → loop.accepted_hashes"]
    RETAKE["retake → request_recapture(failing_metric, hint_box)"]
    ESCALATE["escalate → human review queue"]
    OVERLAY["overlay.py evidence image<br/>NOT BUILT — SPEC § 12"]
  end

  subgraph CV["OpenCV 5 — opencv-python-headless==5.0.0.93, DNN engine 'new'"]
    M1["1 · localise + rectify<br/>Canny, findContours, approxPolyDP,<br/>HoughLinesP fallback,<br/>getPerspectiveTransform, warpPerspective"]
    M2["2 · focus per tile<br/>Laplacian variance over a 6x8 grid"]
    M3["3 · exposure and contrast<br/>calcHist → clipped_low_frac / clipped_high_frac"]
    M4["4 · specular glare<br/>cvtColor BGR2HSV threshold,<br/>morphologyEx OPEN+CLOSE,<br/>connectedComponentsWithStats"]
    M5["5 · text presence and coverage — CLASSICAL<br/>black-hat morphology (MORPH_CLOSE + subtract),<br/>getStructuringElement, connectedComponentsWithStats"]
    M5DNN["5b · DNN text detector<br/>NOT BUILT — TEXT_DETECTOR='classical',<br/>no weights vendored (models/README.md)"]
    M6["6 · frame-edge crop<br/>rectified quad vs frame border margin"]
    M7["7 · QR / barcode<br/>QRCodeDetector, barcode_BarcodeDetector<br/>payload dropped; only code_decoded survives"]
    M8["8 · duplicate<br/>dHash (resize 9x8) + Hamming vs accepted_hashes"]
  end

  FOOTNOTE["Footnote: AWS App Runner is not used —<br/>closed to new customers 30 Apr 2026. SPEC § 9."]
  LEGEND["LEGEND — solid box or solid edge = built and exercised by tests.<br/>Dashed box or dashed edge = planned, not built; each dashed node<br/>names the issue or SPEC section it is deferred to.<br/>This diagram is drawn AS BUILT; see architecture.md for<br/>where it diverges from SPEC § 16. No AWS COOL service is used."]

  PHONE -->|"POST /inspect, raw image bytes — 4 MB cap; Lambda sync payload cap is 6 MB"| SERVER
  PHONE -.->|"POST /inspect — 4 MB cap; Lambda sync payload cap is 6 MB"| FURL
  PHONE --> REVIEW
  AGENTLANE -.-> SERVER
  SERVER --> REVIEW
  REVIEW -->|"Approve — actor=reviewer"| INVOKE
  SMOKE --> SERVER

  SERVER --> PROC
  FURL -.-> LAMBDA
  LAMBDA --> PROC
  LAMBDA -.-> FUTUREH
  DEPLOYSH -->|"owner-run, no CI"| ECR
  ECR --> LAMBDA
  LAMBDA -.-> S3
  LAMBDA -.-> CW

  PROC -->|"every step, actor=agent"| INVOKE
  INVOKE --> PERC
  PERC --> MEAS
  MEAS --> POLICY
  INVOKE --> POLICY
  POLICY --> VERDICT
  VERDICT --> ACCEPT
  VERDICT --> RETAKE
  VERDICT --> ESCALATE
  RETAKE -->|"new capture, re-measured"| PROC
  ACCEPT -->|"seeds the duplicate measurement of later captures"| M8
  ESCALATE -->|"approve / reject / resolve_duplicate — human only"| INVOKE
  VERDICT -.-> OVERLAY

  PERC --> M1
  M1 --> M2
  M1 --> M3
  M1 --> M4
  M1 --> M5
  M1 --> M6
  M1 --> M7
  M1 --> M8
  M5 -.->|"env-selected alternative, not built"| M5DNN

  class PHONE,REVIEW,SERVER,SMOKE,LAMBDA,ECR,DEPLOYSH,PROC,PERC,MEAS,POLICY,VERDICT,ACCEPT,RETAKE,M1,M2,M3,M4,M5,M6,M7,M8 built
  class AGENTLANE,FURL,FUTUREH,S3,CW,OVERLAY,M5DNN unbuilt
  class INVOKE choke
  class ESCALATE human
  class FOOTNOTE,LEGEND note
```

## Reading the bands

### Client

A phone or laptop browser posts raw image bytes to `POST /inspect`. The edge is annotated
**"≤ 4 MB; Lambda sync payload cap is 6 MB"** because that guard is real in both entry
points: `MAX_BODY_BYTES = 4 * 1024 * 1024` in `app/server.py` and again in
`deploy/handler.py`, and a larger body is rejected with `413 payload_too_large` rather than
decoded from a truncated buffer.

The built UI is the **review lane only** — `app/static/review.html`, whose Approve button
`fetch()`es `POST /approve/:capture_id`. SPEC § 16A also sketched an *agent lane* in an
`index.html`; that lane is not built, so it is drawn dashed.

### Local host and AWS — two entry points, one loop

`app/server.py` (stdlib `ThreadingHTTPServer`, `make run`) and `deploy/handler.py` (Lambda
Function URL, payload format 2.0) are two adapters over the *same* `AgentLoop`. Neither has
its own decision logic; both translate a request into `process_capture` or
`invoke("approve", …, actor="reviewer")` and translate the result back.

The Lambda function is a **container image** on **arm64 / Graviton2**, 2048 MB, Python 3.13,
from the digest-pinned `public.ecr.aws/lambda/python:3.13` base, fed in from **Amazon ECR**
by `deploy/build.sh` and `deploy/deploy.sh` — drawn as a hand-run arrow labelled
**"owner-run, no CI"**, because this repo forbids CI and deploying is an owner action.

The Function URL edge itself is **dashed**: the handler code is built and exercised locally
(`deploy/smoke_local.py` calls `handler.handler()` in-process, Docker-free), but the live
endpoint was never created — deployment was attempted and blocked by the only available
AWS account's Free Plan Service Control Policy, not left undone. See
[`deploy.md`](./deploy.md) for the attempt log.

**Amazon S3** and **Amazon CloudWatch Logs** appear dashed: SPEC § 9 and § 12 describe a
private bucket via `store.py` and one structured log line per trace entry, and neither is
built. Drawing them solid would claim persistence and observability this entry does not have.

### The chokepoint

`agent_loop.invoke(tool, args, actor)` is the emphasised box. Every agent tool call, every
human verb and the review page's Approve button pass through it, and its first act is the
actor guard. Inside it: `perception.inspect()` produces a frozen `Measurements` record (31
fields — numbers, flags, boxes, and provenance; **no pixel data and no decoded text**),
`policy.decide()` walks the 11-rule cascade first-match-wins, and the resulting `Verdict`
selects one of three outcomes — `accept`, `retake`, `escalate`.

### OpenCV 5

`perception.inspect()` expands into the eight measurements, each labelled with the real
OpenCV 5 calls behind it. Rectification runs first and every later measurement reads the
rectified page, which is why blur and glare are reported *by location on the receipt* rather
than as one score for the photograph.

Measurement 5 is marked **CLASSICAL**: `TEXT_DETECTOR = "classical"` in `perception.py`, and
`models/README.md` vendors no weights. The DNN text path SPEC § 16A wanted on the diagram
(`dnn.TextDetectionModel_DB`) is drawn dashed as the unbuilt alternative. `dnn_engine_name()`
still reports OpenCV 5's `new` engine, and that string is recorded in every `Measurements`.

## Where this diverges from SPEC § 16

SPEC § 16 was written before any code existed, as a node-and-edge list for a later goal.
Seven of the things it prescribes were never built, and drawing them solid would have
misrepresented the system — which is itself a stated rejection ground for this competition
("Misrepresents capabilities, results, benchmarks, or the role of human review"). The
diagram above is therefore drawn **as built**, and the divergences are recorded here rather
than hidden:

| SPEC § 16 says | As built |
|---|---|
| `apply.py` is the single chokepoint | The chokepoint is `agent_loop.invoke(tool, args, actor)`. `apply.py` does not exist. |
| Side arrows to a private **Amazon S3** bucket | Not built (`store.py`, SPEC § 12) — drawn dashed. |
| Side arrows to **Amazon CloudWatch Logs**, one line per trace entry | Not wired — drawn dashed. The trace exists in memory and over `GET /trace/:id`. |
| Measurement 5 marked `dnn.TextDetectionModel_DB` | The built path is classical morphology; `TEXT_DETECTOR = "classical"`, no weights vendored. The DNN path is drawn dashed. |
| An `index.html` with an **agent lane** and a review lane | Only the review lane exists, as `app/static/review.html`. The agent lane is drawn dashed. |
| An evidence-overlay image on every verdict | `overlay.py` is not built (SPEC § 12) — drawn dashed. |
| All **six** human-only verbs in the review lane | Three are built (`approve`, `reject`, `resolve_duplicate`); `override`, `discard` and `close_batch` are not, and `agent_loop.py`'s own docstring says so. See [`agent-workflow.md`](./agent-workflow.md). |

One more divergence in the other direction: SPEC § 16A drew a single AWS entry point, and
the entry as built has two — the local `app/server.py` and the Lambda `deploy/handler.py` —
so the diagram carries a local band that § 16 did not anticipate. Both are adapters over one
loop, which is why the chokepoint appears once and not twice.

**SPEC § 16 is deliberately left unrevised.** It is the pre-implementation sketch, kept as
the record of what was intended; this file is the record of what was built, and the
difference between the two is stated above rather than quietly edited away.
