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
planned, not built.** Every dashed node names what it waits on (a planned module, or the
AWS account block), so a reader can tell at a glance what runs today from what is on paper.
The one heavily outlined box, `agent_loop.invoke(tool, args, actor)`, is the single
chokepoint: every arrow from the HTTP routes, from the MCP server, from `process_capture`, and
from the review page's buttons goes *into* it, and none route around it.

```mermaid
%% Second Look — architecture, drawn AS BUILT (not as the pre-code design sketched it).
%% Solid = built and exercised by tests. Dashed = planned, not built; each dashed node
%% names what it waits on. Source of truth: src/, app/, deploy/.
flowchart LR
  classDef built fill:#ffffff,stroke:#333333,stroke-width:1px,color:#111111
  classDef unbuilt fill:#f5f5f5,stroke:#999999,stroke-width:1px,stroke-dasharray: 6 4,color:#555555
  classDef choke fill:#fff3cd,stroke:#b8860b,stroke-width:3px,color:#111111
  classDef human fill:#e8f0fe,stroke:#3367d6,stroke-width:2px,color:#111111
  classDef note fill:#fafafa,stroke:#cccccc,stroke-width:1px,color:#444444

  subgraph CLIENT["Client"]
    PHONE["Phone, laptop or curl"]
    REVIEW["app/static/review.html — the review lane<br/>overlay, clause that fired, Approve / Reject / resolve duplicate<br/>Authorization: Bearer reviewer token"]
    MCPCLIENT["An MCP client (an LLM agent)"]
    AGENTLANE["index.html agent lane<br/>NOT BUILT — design only, no code"]
  end

  subgraph LOCAL["Local host — make run"]
    SERVER["app/server.py<br/>stdlib ThreadingHTTPServer, 127.0.0.1:8080<br/>(HOST, PORT override)"]
    SMOKE["app/smoke.py — make smoke"]
    MCP["app/mcp_server.py — stdio MCP<br/>agent tools and reads only, never a human verb"]
  end

  subgraph AWS["AWS"]
    FURL["Lambda Function URL<br/>HTTPS, public, auth-type NONE<br/>BLOCKED — account SCP denies lambda:CreateFunction"]
    EC2["EC2 t3.micro, ap-southeast-2 — app/server.py on port 80<br/>deploy/ec2/Dockerfile + user-data.sh<br/>PREPARED, NOT LAUNCHED — owner clicks Launch"]
    LAMBDA["deploy/handler.py<br/>Lambda container image, payload format 2.0<br/>arm64 / Graviton2, 2048 MB, Python 3.13<br/>MAX_BODY_BYTES = 4 MB"]
    FUTUREH["src/secondlook/handler.py<br/>NOT BUILT — planned module —<br/>deploy/handler.py is the interim stand-in"]
    ECR["Amazon ECR<br/>public.ecr.aws/lambda/python:3.13 base"]
    DEPLOYSH["deploy/build.sh + deploy/deploy.sh<br/>owner-run, no CI"]
    S3["Amazon S3 private bucket<br/>NOT BUILT — waits on store.py"]
    CW["Amazon CloudWatch Logs<br/>NOT WIRED — no per-trace-entry log lines"]
  end

  subgraph CORE["Agent loop — one chokepoint for agent and human alike"]
    SERVICE["service.py — the HTTP routes, written once<br/>reviewer routes need the token (401 without)<br/>MAX_BODY_BYTES = 4 MB"]
    INVOKE["agent_loop.invoke(tool, args, actor)<br/>HUMAN_VERBS need actor=reviewer<br/>AGENT_TOOLS need actor=agent, and a received or measured capture<br/>every mutation passes here or not at all"]
    PROC["agent_loop.process_capture<br/>perception → decision → action;<br/>a no-op once state == escalated"]
    PERC["perception.inspect() — the eight measurements, timed"]
    MEAS["Measurements — 31 frozen fields<br/>numbers, flags, boxes; no pixels, no decoded text"]
    POLICY["policy.decide() — 11-rule cascade, first match wins"]
    VERDICT["Verdict — outcome, rule_id, reason_code, hint_box, firings"]
    ACCEPT["accept → _mark_accepted → loop.accepted_hashes"]
    RETAKE["retake → request_recapture(failing_metric, hint_box)"]
    ESCALATE["escalate → human review queue"]
    OVERLAY["overlay.py evidence image<br/>drawn per request with OpenCV, never stored<br/>GET /overlay/:id, reviewer token"]
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

  FOOTNOTE["Footnote: AWS App Runner is not used —<br/>closed to new customers 30 Apr 2026. See report.md § 5."]
  LEGEND["LEGEND — solid box or solid edge = built and exercised by tests.<br/>Dashed box or dashed edge = planned, not built; each dashed node<br/>names the module or step it waits on.<br/>This diagram is drawn AS BUILT; see architecture.md for<br/>where it diverges from the pre-code design. No AWS COOL service is used."]

  PHONE -->|"POST /inspect, /retake/:id — raw image bytes, 4 MB cap"| SERVER
  PHONE -.->|"POST /inspect — 4 MB cap; Lambda sync payload cap is 6 MB"| FURL
  PHONE -.->|"the same routes, plain HTTP"| EC2
  PHONE --> REVIEW
  AGENTLANE -.-> SERVER
  SERVER --> REVIEW
  REVIEW -->|"approve / reject / resolve_duplicate — token, actor=reviewer"| SERVICE
  SMOKE --> SERVER
  MCPCLIENT -->|"JSON-RPC on stdio"| MCP
  MCP -->|"actor=agent"| INVOKE

  SERVER --> SERVICE
  EC2 -.-> SERVICE
  FURL -.-> LAMBDA
  LAMBDA --> SERVICE
  SERVICE --> PROC
  SERVICE -->|"human verbs, reads"| INVOKE
  SERVICE --> OVERLAY
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
  VERDICT --> OVERLAY

  PERC --> M1
  M1 --> M2
  M1 --> M3
  M1 --> M4
  M1 --> M5
  M1 --> M6
  M1 --> M7
  M1 --> M8
  M5 -.->|"unbuilt alternative"| M5DNN

  class PHONE,REVIEW,SERVER,SMOKE,MCP,MCPCLIENT,SERVICE,LAMBDA,ECR,DEPLOYSH,PROC,PERC,MEAS,POLICY,VERDICT,ACCEPT,RETAKE,OVERLAY,M1,M2,M3,M4,M5,M6,M7,M8 built
  class AGENTLANE,FURL,EC2,FUTUREH,S3,CW,M5DNN unbuilt
  class INVOKE choke
  class ESCALATE human
  class FOOTNOTE,LEGEND note
```

## Reading the bands

### Client

A phone, laptop or `curl` posts raw image bytes to `POST /inspect`, and a retake photo to
`POST /retake/:id`. The 4 MB cap is real on every HTTP path: `MAX_BODY_BYTES = 4 * 1024 * 1024`
in `src/secondlook/service.py`, pre-checked from `Content-Length` in `app/server.py`, and a
larger body is rejected with `413 payload_too_large` rather than decoded from a truncated
buffer. An MCP client (an LLM agent) talks JSON-RPC over stdio to `app/mcp_server.py`.

The built UI is the **review lane** — `app/static/review.html`, which shows each escalated
capture's evidence overlay, the clause that fired and its key measurements, and whose Approve,
Reject and duplicate buttons `fetch()` the reviewer routes with the reviewer token. The
pre-code design also sketched an *agent lane* in an `index.html`; that lane is not built, so it
is drawn dashed.

### Local host and AWS — two entry points, one loop

`app/server.py` (stdlib `ThreadingHTTPServer`, `make run`, and the EC2 image) and
`deploy/handler.py` (Lambda Function URL, payload format 2.0) are two adapters over the *same*
routes, `src/secondlook/service.py`, and through them the same `AgentLoop`. Neither has its own
decision logic; each translates its request shape into one `Service.handle(...)` call, and the
routes are `process_capture` or `invoke(...)` calls. The reviewer routes check the reviewer
token before any `invoke()`. `app/mcp_server.py` is a third adapter, for the agent side only.

The Lambda function is a **container image** on **arm64 / Graviton2**, 2048 MB, Python 3.13,
from the `public.ecr.aws/lambda/python:3.13` base, fed in from **Amazon ECR**
by `deploy/build.sh` and `deploy/deploy.sh` — drawn as a hand-run arrow labelled
**"owner-run, no CI"**, because this repo forbids CI and deploying is an owner action.

The Function URL edge itself is **dashed**: the handler code is built and exercised locally
(`deploy/smoke_local.py` calls `handler.handler()` in-process, Docker-free), but the live
endpoint was never created — deployment was attempted and blocked by the only available
AWS account's Free Plan Service Control Policy, not left undone. See
[`deploy.md`](./deploy.md) for the attempt log.

The **EC2** node is dashed too: one `t3.micro` in `ap-southeast-2` running `app/server.py` from
`deploy/ec2/Dockerfile`, built on first boot by `deploy/ec2/user-data.sh`. Every console field
is prepared in [`deploy.md`](./deploy.md#ec2-console-deploy); it becomes solid once the owner
has launched it and its verification output is recorded.

**Amazon S3** and **Amazon CloudWatch Logs** appear dashed: the design calls for a private
bucket behind a `store.py` module and one structured log line per trace entry, and neither is
built. Drawing them solid would claim persistence and observability this entry does not have.

### The chokepoint

`agent_loop.invoke(tool, args, actor)` is the emphasised box. Every agent tool call, every
human verb and every review-page button pass through it. Its first act is the actor guard;
each agent tool then checks the capture's state and refuses anything that is not `received` or
`measured`, so no agent call can move an escalated, waiting or decided capture. Inside it: `perception.inspect()` produces a frozen `Measurements` record (31
fields — numbers, flags, boxes, and provenance; **no pixel data and no decoded text**),
`policy.decide()` walks the 11-rule cascade first-match-wins, and the resulting `Verdict`
selects one of three outcomes — `accept`, `retake`, `escalate`. `overlay.py` draws the
measurements back onto the image for the reviewer, per request, and stores nothing.

### OpenCV 5

`perception.inspect()` expands into the eight measurements, each labelled with the real
OpenCV 5 calls behind it. Rectification runs first and every later measurement reads the
rectified page, which is why blur and glare are reported *by location on the receipt* rather
than as one score for the photograph.

Measurement 5 is marked **CLASSICAL**: `TEXT_DETECTOR = "classical"` in `perception.py`, and
`models/README.md` vendors no weights. The DNN text path the design wanted on the diagram
(`dnn.TextDetectionModel_DB`) is drawn dashed as the unbuilt alternative. `dnn_engine_name()`
still reports OpenCV 5's `new` engine, and that string is recorded in every `Measurements`.

## Where this diverges from the pre-code design

The diagram's node-and-edge list was written before any code existed, as part of the entry's
design notes (not published in this repository). Seven of the things it prescribes differ
from what was built (the evidence overlay has since been built, differently), and drawing
them as designed would have misrepresented the system — which is itself a
stated rejection ground for this competition ("Misrepresents capabilities, results,
benchmarks, or the role of human review"). The diagram above is therefore drawn **as
built**, and the divergences are recorded here rather than hidden:

| The pre-code design says | As built |
|---|---|
| `apply.py` is the single chokepoint | The chokepoint is `agent_loop.invoke(tool, args, actor)`. `apply.py` does not exist. |
| Side arrows to a private **Amazon S3** bucket | Not built (it waits on a `store.py` module) — drawn dashed. |
| Side arrows to **Amazon CloudWatch Logs**, one line per trace entry | Not wired — drawn dashed. The trace exists in memory and over `GET /trace/:id`. |
| Measurement 5 marked `dnn.TextDetectionModel_DB` | The built path is classical morphology; `TEXT_DETECTOR = "classical"`, no weights vendored. The DNN path is drawn dashed. |
| An `index.html` with an **agent lane** and a review lane | Only the review lane exists, as `app/static/review.html`. The agent lane is drawn dashed. |
| An evidence-overlay image on every verdict | Built after submission as `overlay.py`, drawn per request for the reviewer (`GET /overlay/:id`) rather than stored with every verdict. |
| All **six** human-only verbs in the review lane | Three are built (`approve`, `reject`, `resolve_duplicate`), each with an HTTP route and a review-page button; `override`, `discard` and `close_batch` are not, and `agent_loop.py`'s own docstring says so. See [`agent-workflow.md`](./agent-workflow.md). |

Divergences in the other direction: the design drew a single AWS entry point, and the entry as
built has three adapters — the local and EC2 `app/server.py`, the Lambda `deploy/handler.py`,
and the stdio `app/mcp_server.py` — so the diagram carries a local band and an EC2 node the
design did not anticipate. All are adapters over one loop, which is why the chokepoint appears
once and not three times.

**The design sketch is deliberately left unrevised.** It is the record of what was
intended; this file is the record of what was built, and the difference between the two is
stated above rather than quietly edited away.
