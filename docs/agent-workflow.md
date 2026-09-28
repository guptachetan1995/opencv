# Second Look — agent workflow

The diagram the Agentic Vision Award asks for: "An agent workflow diagram showing
perception, decision or orchestration, and action."

- Source: [`agent-workflow.mmd`](./agent-workflow.mmd) (Mermaid)
- Exported image: [`agent-workflow.svg`](./agent-workflow.svg)

It is drawn as a **cycle, not a pipeline**. Two edges close the loop — the retake edge back
into perception, and the accept edge that seeds the duplicate measurement of later captures
— and those loop-backs are the qualifying claim, not decoration.

## Legend

**Solid box or solid edge = built and exercised by tests. Dashed box or dashed edge =
planned, not built.** `override`, `discard` and `close_batch` are drawn dashed because
`agent_loop.py`'s own module docstring names them as not implemented. The heavily outlined
box is `agent_loop.invoke(tool, args, actor)` — every lane's calls land there.

```mermaid
%% Second Look — agent workflow: perception → decision/orchestration → action, AS BUILT.
%% It is a cycle, not a pipeline: the retake edge and the accept edge both feed back into
%% perception, and that loop-back is the Agentic Vision qualifying claim.
%% Solid = built and exercised by tests. Dashed = planned, not built.
flowchart TD
  classDef built fill:#ffffff,stroke:#333333,stroke-width:1px,color:#111111
  classDef unbuilt fill:#f5f5f5,stroke:#999999,stroke-width:1px,stroke-dasharray: 6 4,color:#555555
  classDef choke fill:#fff3cd,stroke:#b8860b,stroke-width:3px,color:#111111
  classDef human fill:#e8f0fe,stroke:#3367d6,stroke-width:2px,color:#111111
  classDef note fill:#fafafa,stroke:#cccccc,stroke-width:1px,color:#444444
  classDef beat fill:#e6f4ea,stroke:#137333,stroke-width:2px,color:#111111
  classDef escalate fill:#fde7e9,stroke:#c5221f,stroke-width:1px,color:#111111
  classDef retake fill:#fef7e0,stroke:#b06000,stroke-width:1px,color:#111111

  CHOKE["agent_loop.invoke(tool, args, actor) — THE ONE CHOKEPOINT<br/>HUMAN_VERBS refuse actor != 'reviewer'; AGENT_TOOLS refuse actor != 'agent',<br/>and refuse any capture that is not received or measured (StateError).<br/>Every box below that says invoke(...) lands here; there is no second path.<br/>The review page's buttons and the MCP server call it exactly as the loop does."]

  subgraph PERCEPTION["1 · Perception"]
    OPEN["open_capture(image, parent_id) → attach_image<br/>ungated plumbing, not a gated tool"]
    INSPECT["invoke('inspect_capture', ..., actor='agent')"]
    INSPECTFN["perception.inspect() — OpenCV 5, 8 measurements, timed"]
    BUNDLE["Measurements — quad + rectify · focus per tile · exposure ·<br/>glare · text coverage · edge touch · QR/barcode · dHash duplicate"]
  end

  subgraph DECISION["2 · Decision and orchestration"]
    DECIDE["invoke('decide_capture', ..., actor='agent')"]
    CASCADE["policy.decide() — the committed threshold table,<br/>evaluated in order, FIRST MATCH WINS,<br/>every clause recorded in verdict.firings"]
    R1["1 · not_a_document → escalate<br/>quad_found == false OR text_coverage_fraction < 0.02"]
    R2["2 · two_documents → escalate<br/>second_quad_area_fraction > 0.05"]
    R3["3 · suspected_duplicate → escalate<br/>nearest_distance <= 6"]
    R4["4 · persistent_defect → escalate<br/>attempt >= 3"]
    R5["5 · bottom_edge_clipped → retake<br/>edge_touch_sides contains 'bottom' AND bottom_band_has_text"]
    R6["6 · glare_over_total → retake<br/>glare_over_text_frac > 0.15"]
    R7["7 · out_of_focus → retake<br/>focus_min_tile < 2.0 AND code_decoded == false"]
    R8["8 · underexposed → retake<br/>clipped_low_frac > 0.25"]
    R9["9 · overexposed → retake<br/>clipped_high_frac > 0.40"]
    R10["10 · uncertain → escalate<br/>within the margin of any threshold above"]
    R11["11 · accept → accept<br/>every metric comfortably inside its band"]
  end

  subgraph ACTION["3 · Action — the measurement picks the next call"]
    RETAKE["invoke('request_recapture', {failing_metric, hint_box}, actor='agent')"]
    ESC["invoke('escalate', {reason}, actor='agent')"]
    ACC["accept → _mark_accepted → loop.accepted_hashes"]
  end

  subgraph HUMAN["4 · Human review lane — actor='reviewer' only"]
    QUEUE["Human review queue.<br/>process_capture is a NO-OP once state == 'escalated',<br/>and every agent tool refuses the capture:<br/>nothing advances it until a person calls<br/>invoke(verb, args, actor='reviewer') — over HTTP, with the reviewer token.<br/>The reviewer sees the evidence overlay and the clause that fired."]
    APPROVE["approve — POST /approve/:id<br/>refuses a suspected_duplicate until resolve_duplicate has run"]
    REJECT["reject — POST /reject/:id"]
    RESOLVE["resolve_duplicate — POST /resolve_duplicate/:id"]
    OVERRIDE["override — NOT BUILT"]
    DISCARD["discard — NOT BUILT"]
    CLOSE["close_batch — NOT BUILT"]
  end

  BEAT["THE QUALIFYING BEAT — visual evidence changes what the system does next.<br/>glare_text.jpg fires rule 6, glare_over_total (glare_over_text_frac).<br/>The retake removes the glare but crops the page, so the NEXT capture fires<br/>rule 5, bottom_edge_clipped (edge_touch_sides) — a DIFFERENT rule, chosen by a<br/>DIFFERENT metric, on a DIFFERENT image. Asserted end to end by tools/run_demo.py<br/>and measured as the retake-convergence set in docs/evaluation.md."]

  TRACE["Trace ribbon — every invoke() records TraceEntry(seq, actor, action, inputs, outputs, caused_by).<br/>trace_chain() walks parent_id back to the root capture and renumbers seq across the whole chain,<br/>so caused_by points at the node that produced each decision."]

  CALLOUT1["Callout A — code_decoded == false is a CLAUSE of rule 7:<br/>a decoded QR cancels the retake a soft-focus page would otherwise get.<br/>A measurement can call OFF an action, not only call one."]
  CALLOUT2["Callout B — attempt >= 3 fires rule 4, persistent_defect (escalate):<br/>after two retakes the agent stops guessing and asks a person."]
  LEGEND["LEGEND — solid box or solid edge = built and exercised by tests.<br/>Dashed box or dashed edge = planned, not built; override, discard and close_batch<br/>are named unbuilt in agent_loop.py's own docstring.<br/>Drawn AS BUILT; agent-workflow.md records where this diverges from the pre-code design."]

  OPEN --> INSPECT
  INSPECT --> INSPECTFN
  INSPECTFN --> BUNDLE
  BUNDLE --> DECIDE
  DECIDE --> CASCADE
  CASCADE --> R1
  R1 -->|"no match"| R2
  R2 -->|"no match"| R3
  R3 -->|"no match"| R4
  R4 -->|"no match"| R5
  R5 -->|"no match"| R6
  R6 -->|"no match"| R7
  R7 -->|"no match"| R8
  R8 -->|"no match"| R9
  R9 -->|"no match"| R10
  R10 -->|"no match"| R11

  R1 --> ESC
  R2 --> ESC
  R3 --> ESC
  R4 --> ESC
  R10 --> ESC
  R5 --> RETAKE
  R6 --> RETAKE
  R7 --> RETAKE
  R8 --> RETAKE
  R9 --> RETAKE
  R11 --> ACC

  RETAKE ==>|"a new image, measured again"| BEAT
  BEAT ==>|"open_capture(parent_id) → attach_image → process_capture"| OPEN
  ACC -->|"the accepted phash seeds the duplicate measurement of LATER captures"| BUNDLE

  ESC --> QUEUE
  QUEUE --> APPROVE
  QUEUE --> REJECT
  QUEUE --> RESOLVE
  QUEUE -.-> OVERRIDE
  QUEUE -.-> DISCARD
  QUEUE -.-> CLOSE
  RESOLVE --> APPROVE
  APPROVE -->|"state = accepted"| ACC

  INSPECT -.->|"through the chokepoint"| CHOKE
  DECIDE -.->|"through the chokepoint"| CHOKE
  RETAKE -.->|"through the chokepoint"| CHOKE
  ESC -.->|"through the chokepoint"| CHOKE
  QUEUE -.->|"the same chokepoint, actor='reviewer'"| CHOKE
  CHOKE -.-> TRACE

  R7 -.-> CALLOUT1
  R4 -.-> CALLOUT2

  class OPEN,INSPECT,INSPECTFN,BUNDLE,DECIDE,CASCADE,R1,R2,R3,R4,R5,R6,R7,R8,R9,R10,R11,ACC,TRACE built
  class RETAKE retake
  class ESC escalate
  class QUEUE,APPROVE,REJECT,RESOLVE human
  class OVERRIDE,DISCARD,CLOSE unbuilt
  class CHOKE choke
  class BEAT beat
  class CALLOUT1,CALLOUT2,LEGEND note
```

## 1 · Perception

`open_capture(image, parent_id)` and `attach_image` are deliberately ungated plumbing — they
create a slot and put bytes in it, and mutate nothing a verdict depends on except the retake
`attempt` counter, derived from `parent_id` rather than caller-supplied. The first gated
call is `invoke("inspect_capture", …, actor="agent")`, which runs `perception.inspect()`:
rectify first, then focus per tile, exposure, glare, text coverage, frame-edge crop,
QR/barcode and the perceptual hash, each timed into `elapsed_ms`. The output is one frozen
`Measurements` record of numbers, flags and box coordinates. No pixels and no decoded text
travel any further.

## 2 · Decision and orchestration

`invoke("decide_capture", …, actor="agent")` runs `policy.decide()` against
`src/secondlook/policy.toml` — a committed threshold table, no model and no randomness. The
cascade is drawn as an ordered ladder because **its order is the policy**: rules are
evaluated top to bottom and the first match wins. Escalating rules sit above retake rules on
purpose, so "this is not a receipt" or "I have seen this receipt already" beats "the light
was bad". Every clause evaluated — matched or not — is recorded in `verdict.firings`, which
is what makes a verdict auditable after the fact.

Rule 10, `uncertain`, is the safety valve: a capture that lands within a margin of any
threshold above goes to a person rather than being resolved by a hair's width. Rule 11 only
accepts when everything is comfortably inside its band.

## 3 · Action

The verdict picks exactly one next call, and the edge into it is labelled with the metric
that chose it:

| Rule | Metric that fired it | Next call |
|---|---|---|
| `bottom_edge_clipped` | `edge_touch_sides` (+ `bottom_band_has_text`) | `request_recapture` |
| `glare_over_total` | `glare_over_text_frac` | `request_recapture` |
| `out_of_focus` | `focus_min_tile` (unless `code_decoded`) | `request_recapture` |
| `underexposed` | `clipped_low_frac` | `request_recapture` |
| `overexposed` | `clipped_high_frac` | `request_recapture` |
| `not_a_document`, `two_documents`, `suspected_duplicate`, `persistent_defect`, `uncertain` | `quad_found` / `text_coverage_fraction`, `second_quad_area_fraction`, `nearest_distance`, `attempt`, any margin | `escalate` |
| `accept` | all of them, comfortably | `_mark_accepted` |

`process_capture` makes those calls itself — a person does not, and neither does a test
script. `request_recapture` names the one failing metric and the hint box for the region it
failed in, opens a successor capture with `parent_id` set, and the loop starts again on the
new image.

Two callouts on the diagram are worth reading twice. **Callout A**: `code_decoded == false`
is a *clause* of `out_of_focus`, so a decoded QR code cancels a retake that a soft-focus page
would otherwise have been asked for — a measurement calling an action *off*. **Callout B**:
`attempt >= 3` fires `persistent_defect` and escalates, so after two retakes the agent stops
guessing and hands the capture to a person.

## 4 · Human review lane

An escalated capture stops moving. `process_capture` returns immediately once
`state == "escalated"`, and every agent tool raises `StateError` for a capture that is not
`received` or `measured` — so neither the loop nor an agent calling its tools directly can
re-decide it, request a retake of it or move it anywhere. Nothing advances it until a person
calls `invoke(verb, …, actor="reviewer")`. This is a mechanism, not a promise: there is no
timer that eventually auto-approves and no agent path that reaches the accepted state.
`tests/test_agent_loop.py` replays the escape that the state guard closes (re-decide the
escalated capture, then request a retake of it) and asserts every agent tool is refused.

The guard that enforces it lives in `invoke()` itself:

```python
if tool in HUMAN_VERBS and actor != "reviewer":
    raise PermissionError(f"{tool!r} is human-only; actor was {actor!r}")
if tool in AGENT_TOOLS and actor != "agent":
    raise PermissionError(f"{tool!r} is an agent tool; actor was {actor!r}")
```

`approve`, `reject` and `resolve_duplicate` are built, each with an HTTP route and a button
on the review page, which shows the reviewer the evidence overlay and the clause that fired.
Over HTTP those routes need the reviewer token (`Authorization: Bearer …`) and answer `401`
without it. `override`, `discard` and `close_batch` are drawn dashed because they are not
built. One extra ordering rule is drawn in:
`approve` **refuses** a capture escalated as `suspected_duplicate` until `resolve_duplicate`
has run, so a person cannot wave a possible duplicate through in one click.

## The qualifying beat

The award's own words: "the visual evidence must change what the system does next". Here is
the exact beat, and it is asserted end to end by
[`tools/run_demo.py`](../tools/run_demo.py):

1. `glare_text.jpg` is measured. `glare_over_text_frac` is over 0.15, so rule 6,
   `glare_over_total`, fires. Outcome: **retake**, with the failing metric
   `glare_over_text_frac` and a hint box over the glare.
2. The retake arrives — `crop_bottom.jpg`, the same underlying receipt, the light moved. The
   glare is gone. `glare_over_text_frac` no longer fires.
3. But the new framing clipped the page: `edge_touch_sides` contains `bottom` and the bottom
   band has text, so rule 5, `bottom_edge_clipped`, fires. Outcome: **retake** again — from a
   **different rule**, chosen by a **different metric**, on a **different image**.
4. `clean_a.jpg` arrives and rule 11 accepts it.

Nothing about step 3 was scheduled. It is the second image's own measurements selecting the
second instruction; had the retake been clean, rule 11 would have accepted it instead — and
that is exactly what the third step shows.

`docs/evaluation.md` measures this as its **retake-convergence sequence set**: six scripted
sequences, of which the `glare_text → crop_bottom → clean_a` chain converges in 2 retakes,
and the deliberately unfixable `blur_4 → blur_4 → blur_4` chain correctly does *not*
converge — it escalates as `persistent_defect` on the third decision. Convergence overall:
**5/6 (83.3%)**.

## Where this diverges from the pre-code design

The workflow diagram's outline was written before the loop existed, as part of the entry's
design notes (not published in this repository). Two of its prescriptions are drawn
differently here, and the reason is accuracy rather than preference:

- The outline asks for a human review lane containing all six human-only verbs. Only three
  are built. All six appear, but `override`, `discard` and `close_batch` are dashed and
  labelled NOT BUILT.
- The outline's perception node is `inspect_capture` with the eight metrics drawn as a
  bundle; as built, the ungated `open_capture` / `attach_image` plumbing sits before it and
  is drawn, because otherwise the loop-back edge has nowhere to land.

The outline is left unrevised on purpose — it is the record of the pre-implementation
intention. See [`architecture.md`](./architecture.md#where-this-diverges-from-the-pre-code-design)
for the same treatment of the architecture diagram.
