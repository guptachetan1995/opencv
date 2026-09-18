# Second Look — demo video script and shot list

This is the word-for-word script and shot list for the submission video. **The owner records,
uploads and submits; this repository never records, uploads or publishes anything.** Total
runtime is **4:28 (268 s)**, against a hard limit of five minutes. Every claim narrated below
was executed against the locally running app before this file was written, and the output
quoted in each beat's "On screen you should see" block is the real terminal output of that
run — not a reconstruction.

---

## 1. The five-minute rule and the budget

The rules cap the video at **five minutes — 300 s** (`docs/submission.md`'s submission-artifacts
table: "**no more than five minutes**"). Over it, the entry is not judged. The goal this script
answers asks for **10 % headroom** on top: 300 × 0.10 = 30 s, so the working ceiling is
300 − 30 = **270 s = 4:30**.

**Chosen total: 4:28 = 268 s.** That is 2 s under the 4:30 ceiling and 32 s under the 5:00 limit
— **(300 − 268) ÷ 300 ≈ 10.7 % headroom**, which clears the 10 % requirement.

### A beat's duration is speech **plus** action, never speech alone

Every row of the table below satisfies:

> **duration ≥ (spoken words ÷ 2.5) + action seconds + at least 1 s of margin**

- **2.5 words/s = 150 wpm** — an unhurried narration pace. It is used for every number below and
  must not be silently changed; the whole budget rests on it.
- **Spoken-word count**, the convention behind every figure here: whitespace tokens, with two
  adjustments. A backticked identifier counts as the number of words it takes to *say* —
  `caused_by` = 2, `invoke` = 1, `reviewer` = 1, `/approve` = 2 ("slash approve"). And
  **standalone punctuation tokens do not count as spoken words**: a free-standing em dash `—`
  between two clauses is a breath, not a word, and contributes 0. A naive `wc -w` both
  under-counts identifier-heavy narration and over-counts the dashes.
- **Action seconds** = deliberate dead air where narration is paused for something to land: the
  shot settling, a command's output painting and being read, a window cut, a page re-render, a
  diagram zoom settling. Each beat's figure is itemised in its **Budget** line in section 5.
- **At least 1 s of margin** per beat, on top of both, so one fumbled sentence does not overrun.

### The beat budget

| # | Beat | Start–End | Duration | Spoken words | Speech @ 2.5 w/s | Action | Margin |
|---|---|---|---|---|---|---|---|
| 1 | Hook — a bad capture, measured, answered | 0:00–0:36 | 36 s | 74 | 29.6 s | 5 s | 1.4 s |
| 2 | Team | 0:36–0:59 | 23 s | 46 | 18.4 s | 3 s | 1.6 s |
| 3 | The app working on real inputs | 0:59–1:45 | 46 s | 91 | 36.4 s | 8 s | 1.6 s |
| 4 | The trace — the measurement chose the next call | 1:45–2:35 | 50 s | 107 | 42.8 s | 6 s | 1.2 s |
| 5 | The human gate | 2:35–3:19 | 44 s | 80 | 32.0 s | 11 s | 1.0 s |
| 6 | Architecture | 3:19–4:03 | 44 s | 90 | 36.0 s | 6 s | 2.0 s |
| 7 | Principal results | 4:03–4:28 | 25 s | 52 | 20.8 s | 3 s | 1.2 s |

- Durations: 36 + 23 + 46 + 50 + 44 + 44 + 25 = **268 s = 4:28** — 2 s under the 270 s ceiling,
  32 s under the 300 s limit.
- Spoken words: 74 + 46 + 91 + 107 + 80 + 90 + 52 = **540** → 540 ÷ 2.5 = **216.0 s of speech**.
- Action: 5 + 3 + 8 + 6 + 11 + 6 + 3 = **42 s**.
- 216.0 + 42 = **258.0 s of committed time inside a 268 s budget**, leaving **10.0 s of
  aggregate margin** and a split of **80.6 % speech / 19.4 % action-and-margin**.
- Per-beat margins: 1.4 + 1.6 + 1.6 + 1.2 + 1.0 + 2.0 + 1.2 = **10.0 s**, which is the same
  number arrived at from the other direction. The two agree, so the table is internally
  consistent.

**If any narration block below is reworded, re-count that block under the convention above and
re-check its row.** If the margin falls under 1 s, trim the wording back or raise that beat's
duration and re-add the seven — the sum must stay at or under 270 s.

---

## 2. What the video must show

The rules require four things, and `docs/submission.md` sharpens the requirement to "all four,
or the requirement is not met". The script adds two more because they are what this entry is
for. **No beat here is optional; cutting one for time breaks a rule rather than saving seconds.**

| Required element | Source | Beat that covers it |
|---|---|---|
| The team | competition rules, via `docs/submission.md` | 2 |
| The application working | competition rules, via `docs/submission.md` | 1, 3, 5 |
| Its architecture | competition rules, via `docs/submission.md` | 6 |
| Its principal results | competition rules, via `docs/submission.md` | 7 |
| A visual result changing the next action | Agentic Vision Award criterion | 4 |
| A human gate that is real, not rhetorical | this entry's own claim | 5 |

---

## 3. Recording setup

| Item | Setting | Why |
|---|---|---|
| Windows | Terminal A (server, never on camera), Terminal B (the one on camera), one browser window, one camera shot for beat 2 | Four sources, no window juggling mid-beat |
| Terminal B width | **at least 210 columns** | `tools/run_demo.py`'s longest output line measured **207 characters**; a wrapped `caused_by` column is unreadable and beat 4 is entirely about reading that column |
| Terminal B height | **at least 30 rows** | `run_demo.py` prints **26 lines**, so the whole run fits with no scrolling |
| Colour scheme | **light mode — browser *and* OS** | `app/static/review.html` sets `color: #1a1a1a` with no body background; a dark-scheme viewer renders it dark-on-dark and it looks broken |
| Terminal font | large enough that `0.9211` is legible at the delivered resolution | Beat 1's whole claim is one number on screen |
| Not on screen | any other tab, notification, editor, or this file | The take is Terminal B, the browser, the diagram, and the owner |

**Recording is a human action.** This repo prepares the script; the owner records the take,
uploads it, and pastes the link into the Devpost form.

---

## 4. Seeded state — start here, every time

Two terminals and one browser window, all set up **before** the recorder starts.

**Terminal A** — the server. Left running, untouched, for the whole take:

```sh
cd entries/opencv
make setup
make run
# second look serving on http://127.0.0.1:8080 (Ctrl+C to stop)
```

**Terminal B** — the driver, the only terminal on camera:

```sh
cd entries/opencv
curl -s http://127.0.0.1:8080/health     # off camera; expect {"status": "ok"}
curl -s http://127.0.0.1:8080/pending    # off camera; expect []  — proves the process is clean
clear
```

**Browser** — one tab, **light mode**, at `http://127.0.0.1:8080/review`. Load it and leave it
alone until beat 5.

### Commands are recalled from history, not typed character by character

This is a **budget item, not a convenience.** The `/inspect` one-liners below are around 300
characters each. Typed live at a realistic on-camera pace they cost roughly 30 s apiece — the
four of them alone would eat two minutes of a four-and-a-half-minute video.

So, off camera and before the recorder starts, the owner runs each of the **seven** on-camera
commands once in Terminal B so it lands in shell history, then `clear`s. On camera each is
recalled with `Ctrl-R` and the distinctive substring below, then Enter.

| Order | Beat | Command | `Ctrl-R` search string |
|---|---|---|---|
| 1 | 1 | `POST /inspect` with `glare_text.jpg`, piped to selector S1 | `glare_text` |
| 2 | 3 | `POST /inspect` with `crop_bottom.jpg`, piped to selector S3 | `crop_bottom` |
| 3 | 3 | `POST /inspect` with `clean_a.jpg`, piped to selector S3 | `clean_a` |
| 4 | 3 | `POST /inspect` with `not_doc.jpg`, piped to selector S3 | `not_doc` |
| 5 | 4 | `.venv/bin/python tools/run_demo.py` | `run_demo` |
| 6 | 5 | `GET /pending`, piped to selector S5a | `pending` |
| 7 | 5 | `GET /trace/c_006`, piped to selector S5b | `trace/c_006` |

Every search string above is unique across the seven, so one `Ctrl-R` and one Enter reaches the
right command with no second guess and no scrolling through history on camera.

**Nothing is hidden by recalling from history.** The full command text is on screen, verbatim,
before Enter is pressed — that is the point, and it is why the alternative (wrapping the `curl`s
in short shell functions) is deliberately *not* used: a helper named `inspect` would put a layer
between the viewer and the actual HTTP call. The action budgets in section 5 assume recall
(about 1 s), not typing.

**Warning — the off-camera rehearsal POSTs count.** Running the four `/inspect` calls once to
seed shell history advances the server's capture ids exactly as the real take does, so the take
would start at `c_007`. The order is therefore: **pre-load history → restart `make run` →
record.** Getting this wrong is the same failure as trap 8.

### The four field selectors

A raw `/inspect` response carries 31 measurement fields on one line, and `text_boxes` alone runs
to about 40 entries — `python -m json.tool` on it is 200+ lines and unreadable on camera. Each
beat therefore gets a selector that prints only what that beat claims, and nothing else.

```sh
# S1 — beat 1: glare. Prints capture_id, state, verdict, and the metric the rule fired on.
.venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); m=d["measurements"]; v=d["verdict"]; print(d["capture_id"], d["state"]); print(v["outcome"], v["rule_id"], v["hint_box"]); print(v["reason_text"]); print("glare_over_text_frac", m["glare_over_text_frac"], "| threshold 0.15")'

# S3 — beat 3: crop / clean / not-a-document. DIFFERENT metrics from S1.
.venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); m=d["measurements"]; v=d["verdict"]; print(d["capture_id"], d["state"]); print(v["outcome"], v["rule_id"], v["hint_box"]); print(v["reason_text"]); print("edge_touch_sides", m["edge_touch_sides"], "| bottom_band_has_text", m["bottom_band_has_text"], "| quad_found", m["quad_found"])'

# S5a — beat 5: the review queue, one line per waiting capture.
.venv/bin/python -c 'import json,sys; [print(c["capture_id"], c["state"], c["review_reason"]) for c in json.load(sys.stdin)]'

# S5b — beat 5: the trace, one line per entry.
.venv/bin/python -c 'import json,sys; [print(r["seq"], r["actor"], r["action"], r["outputs"], "caused_by", r["caused_by"]) for r in json.load(sys.stdin)]'
```

**S1 and S3 must not be swapped.** `glare_over_text_frac` is `0.9211` for `glare_text.jpg` and
**exactly `0.0` for `crop_bottom.jpg`, `clean_a.jpg` and `not_doc.jpg`** — verified live.
Printing it in beat 3 would put three zeroes on screen next to a narration about a *different*
metric firing a *different* rule, which is the one thing beat 3 exists to show. Beat 3's claim
rests on `edge_touch_sides` and `bottom_band_has_text`, so those are what S3 prints.

**The `0.15` in S1 is typed, not read from the response.** It is the threshold in
`src/secondlook/policy.toml`'s `glare_over_total` rule
(`{ metric = "glare_over_text_frac", op = ">", value = 0.15, margin = 0.03 }`). It is on screen
because it is in the command the viewer watches being run — stated here so nobody mistakes it
for a field the server returned.

**S5a and S5b render Python dicts, not JSON.** `outputs` prints as `{'state': 'accepted'}`
(single-quoted `repr`) because the selector `print`s a `dict`. The `/trace/<capture_id>` route's
own wire format is real JSON — `{"state": "accepted"}` — and `tools/run_demo.py` in beat 4
prints the same `repr` style. So the *screen* is `repr`-styled in beats 4 and 5 consistently;
nothing is mixed, and nothing in the narration turns on the difference. The "On screen" blocks
below are written in `repr` style to match; do not "correct" them to JSON.

### The four `POST /inspect` calls happen in this exact order, and no others

| Order | Beat | Sample | Capture id | Result |
|---|---|---|---|---|
| 1 | 1 | `data/synthetic/glare_text.jpg` | `c_001` | `awaiting_retake` · retake · `glare_over_total` |
| 2 | 3 | `data/synthetic/crop_bottom.jpg` | `c_003` | `awaiting_retake` · retake · `bottom_edge_clipped` |
| 3 | 3 | `data/synthetic/clean_a.jpg` | `c_005` | `accepted` · accept · `accept` |
| 4 | 3 | `data/synthetic/not_doc.jpg` | `c_006` | `escalated` · escalate · `not_a_document` |

`c_002` and `c_004` are the successor slots `request_recapture` opened when the first and second
captures were told to retake. **The skipped ids are real, and beat 3 points at them on camera.**

### Three rules, because breaking any one of them destroys a beat

1. **Defects before clean.** `glare_text.jpg` and `crop_bottom.jpg` must be posted *before*
   `clean_a.jpg`. An accepted capture seeds `loop.accepted_hashes`, and dHash runs on the
   rectified page, so a defect variant of layout "a" hashes close to an accepted `clean_a`.
   Verified: with `clean_a` first, `glare_text` comes back **escalated / `suspected_duplicate`**
   with `nearest_distance = 4` instead of retake, and the hook beat is gone. This is Failure
   Case 1 in [`evaluation.md`](./evaluation.md).
2. **One continuous server session.** Capture ids and hash state accumulate in one in-memory
   `AgentLoop` per process. If any beat is re-taken, restart `make run` and redo *every* earlier
   POST in order, or the ids printed in this script stop matching the screen.
3. **No extra POSTs.** Not even a "let me just check". Any additional `/inspect` shifts every
   later capture id.

---

## 5. The script

Every beat below has the same five parts, in the same order: **Shot**, **Type this**, **On
screen you should see**, **Narration**, **Do not say**. Terminal B is already in
`entries/opencv`, so the commands are written as they are recalled.

### Beat 1 — Hook: a bad capture, measured, answered (0:00–0:36) · 36 s

**Budget.** 74 spoken words = 29.6 s speech · 5 s action (2 s shot settle, 3 s for the response
to paint and be read) · **1.4 s margin** in a 36 s beat.

**Shot.** Terminal B, full screen, empty. One command, recalled from history with `glare_text`.

**Type this:**

```sh
curl -s -w '%{stderr}\nround trip %{time_total}s\n' -X POST --data-binary @data/synthetic/glare_text.jpg \
  -H 'Content-Type: image/jpeg' http://127.0.0.1:8080/inspect | .venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); m=d["measurements"]; v=d["verdict"]; print(d["capture_id"], d["state"]); print(v["outcome"], v["rule_id"], v["hint_box"]); print(v["reason_text"]); print("glare_over_text_frac", m["glare_over_text_frac"], "| threshold 0.15")'
```

**`%{stderr}` is load-bearing.** The obvious form of this command — `-w '\ntotal %{time_total}s\n'`
without `%{stderr}` — **is broken**: `-w` appends its text to *stdout* after the JSON body, so
the selector dies with `json.decoder.JSONDecodeError: Extra data: line 2 column 1`. The
`%{stderr}` directive (curl ≥ 7.63; the recording machine has curl 8.7.1) redirects the rest of
the write-out to **stderr**, so the timing line prints to the terminal while stdout stays pure
JSON for the pipe.

**On screen you should see:**

```
round trip 0.060270s
c_001 awaiting_retake
retake glare_over_total [201, 1006, 462, 141]
Glare is covering the text. Move so the light source is behind you and shoot again.
glare_over_text_frac 0.9211 | threshold 0.15
```

**Only the first line moves.** The `round trip` figure is a live measurement and differs every
run — two dry-run passes on the same machine read `0.060270s` and `0.061311s`. The four lines
below it are deterministic and must match exactly; if they do not, the seeded state is wrong,
so stop and re-read section 4 rather than recording.

**Narration** (74 spoken words · 29.6 s):

> A receipt photographed under a window. Finance finds out it is unreadable at month end — days
> later, when the paper is already in a bin. Second Look measures the photo at capture instead.
> One POST, and OpenCV 5 answers: glare over ninety-two percent of the text against a threshold
> of fifteen, a hint box on the failing region, and an instruction — move the light behind you,
> shoot again. Round trip, well under a second.

**Do not say.** No millisecond figure — not "under fifty milliseconds", not any other number
tighter than the screen. The dry run's `round trip` line read `0.060270s`, and the figure moves
run to run, so **"well under a second" is the claim the screen supports**. The body's own
`elapsed_ms` is a per-stage dict (`localise`, `focus`, `exposure`, `text`, `glare`, `edge`,
`code`, `duplicate`), not a round-trip figure, so it cannot stand in either. Say what the screen
says.

### Beat 2 — Team (0:36–0:59) · 23 s

**Budget.** 46 spoken words = 18.4 s speech · 3 s action (a beat of silence either side of the
talking-head cut) · **1.6 s margin** in a 23 s beat.

**Shot.** Produced as `bin/video/`'s other beats are: a static title card
(`bin/video/out/opencv/frames/beat2-team.html`) — entry name, hackathon and track, byline, and the
framing line — held for the beat, narrated over. No camera segment; the owner's part of video
production stays limited to uploading the finished file, per the standing team practice for every
entry so far.

**Type this:** nothing. This beat is the title card and the voice.

**On screen you should see:** "Second Look" · "OpenCV AI Competition 2026 · Agentic Vision Track" ·
"Chetan Gupta — solo entry" · the framing quote.

**Narration** (46 spoken words · 18.4 s) — read verbatim, name included. The name is the repo's
own byline, `entries/opencv/LICENSE` line 3, `Copyright (c) 2026 Chetan Gupta`:

> I'm Chetan Gupta. Second Look is a solo entry for the OpenCV AI Competition 2026, Agentic
> Vision track. The expensive thing here isn't OCR — it's the latency between a bad capture and
> anyone knowing it was bad, because that latency is what makes the defect permanent.

The three mandatory pieces and what each costs: the name (3 words / 1.2 s), the
solo-entry-and-track line (15 words / 6.0 s), the framing sentence (28 words / 11.2 s) — 18.4 s
inside a 23 s slot. The framing sentence condenses two sentences of `docs/submission.md`'s
Inspiration section into one for speech. **It is not a verbatim quotation and must not be
introduced as one**; read it exactly as written above.

**Do not say.** Nothing about a team, "we", or collaborators. It is a solo entry and the LICENSE
is the only byline.

### Beat 3 — The app working on real inputs (0:59–1:45) · 46 s

**Budget.** 91 spoken words = 36.4 s speech · 8 s action (three verdicts, about 2.7 s of quiet
each so the viewer can read the one on screen) · **1.6 s margin** in a 46 s beat. The `clear`s
and the history recalls happen *while* narrating and are not budgeted separately.

**Shot.** Terminal B. `clear` between each command so each verdict lands alone on an empty
screen.

**Type this**, in order, each recalled from history and each piped to **S3** — not beat 1's S1:

```sh
curl -s -X POST --data-binary @data/synthetic/crop_bottom.jpg \
  -H 'Content-Type: image/jpeg' http://127.0.0.1:8080/inspect | .venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); m=d["measurements"]; v=d["verdict"]; print(d["capture_id"], d["state"]); print(v["outcome"], v["rule_id"], v["hint_box"]); print(v["reason_text"]); print("edge_touch_sides", m["edge_touch_sides"], "| bottom_band_has_text", m["bottom_band_has_text"], "| quad_found", m["quad_found"])'
clear
curl -s -X POST --data-binary @data/synthetic/clean_a.jpg \
  -H 'Content-Type: image/jpeg' http://127.0.0.1:8080/inspect | .venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); m=d["measurements"]; v=d["verdict"]; print(d["capture_id"], d["state"]); print(v["outcome"], v["rule_id"], v["hint_box"]); print(v["reason_text"]); print("edge_touch_sides", m["edge_touch_sides"], "| bottom_band_has_text", m["bottom_band_has_text"], "| quad_found", m["quad_found"])'
clear
curl -s -X POST --data-binary @data/synthetic/not_doc.jpg \
  -H 'Content-Type: image/jpeg' http://127.0.0.1:8080/inspect | .venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); m=d["measurements"]; v=d["verdict"]; print(d["capture_id"], d["state"]); print(v["outcome"], v["rule_id"], v["hint_box"]); print(v["reason_text"]); print("edge_touch_sides", m["edge_touch_sides"], "| bottom_band_has_text", m["bottom_band_has_text"], "| quad_found", m["quad_found"])'
```

**On screen you should see**, one screen at a time:

```
c_003 awaiting_retake
retake bottom_edge_clipped [0, 895, 800, 122]
The bottom of the receipt is outside the frame. Step back and include the total line.
edge_touch_sides ['bottom'] | bottom_band_has_text True | quad_found True
```

```
c_005 accepted
accept accept None
Every measurement is comfortably inside its band.
edge_touch_sides [] | bottom_band_has_text False | quad_found True
```

```
c_006 escalated
escalate not_a_document None
This does not look like a receipt, so a person will take a look.
edge_touch_sides [] | bottom_band_has_text True | quad_found False
```

`not_doc.jpg` also reads `bottom_band_has_text True` — harmless noise from a non-document image,
and **not** what escalated it. `quad_found False` is. Do not narrate the bottom band here.

**Narration** (91 spoken words · 36.4 s). Identifiers are spoken as plain English rather than
read out as snake_case — `bottom_edge_clipped` alone costs 3 spoken words each time it is said,
and the rule id is legible on screen anyway:

> Same endpoint, three more inputs from the committed synthetic set. A receipt with its bottom
> edge out of frame: different metrics fire — the frame edge is touched at the bottom, and there
> is text at the cut — so a different rule and a different instruction: step back, include the
> total line. A clean capture: accepted, no hint box. And something that is not a receipt: no
> document quad found, so the agent does not guess. It escalates. Notice the ids skip. Two of
> them are retake slots the agent already opened.

**Do not say.** Nothing about a drop zone, an evidence overlay, a verdict panel, an agent lane,
or side-by-side rectified pages. `SPEC.md` § 7 describes those; **none of them are built.**

### Beat 4 — The trace: the measurement chose the next call (1:45–2:35) · 50 s

This is the qualifying Agentic Vision beat: **a visual result changed the next action.**

**Budget.** 107 spoken words = 42.8 s speech · 6 s action (recall, the run, and reading down the
`caused_by` column before speaking) · **1.2 s margin** in a 50 s beat.

**Shot.** Terminal B, full screen. The trace block is the **top half** of the output — measured
at 26 lines total, with the `-- trace: glare -> crop retake chain --` block on lines 4 to 12 —
so in a terminal of 30 rows or more the whole run fits and **no scrolling is needed**. The real
constraint is width: the longest line is **207 characters**, so Terminal B must be at least 210
columns or the `caused_by` column wraps and this beat becomes unreadable.

**Why the driver, and not more HTTP.** Over plain HTTP each `POST /inspect` opens an independent
capture with no `parent_id`, so the linked chain with `compare_captures` only exists through the
demo driver. It runs in its **own process with its own in-memory batch** — it does not touch the
server's state, and its capture numbering starts again at `c_001`. That is why its
`successor_id` values read `c_002` and `c_003` while the server's ids in beats 1 and 3 read
`c_001`, `c_003`, `c_005`, `c_006`. **The narration says so on camera**, in the first sentence,
so the reset never looks like a contradiction.

**Type this:**

```sh
.venv/bin/python tools/run_demo.py
```

**On screen you should see** (the first half of the output — the two rows the narration turns on
are `seq 4` and `seq 6`):

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
```

**Narration** (107 spoken words · 42.8 s):

> This driver runs in its own process, so capture numbering restarts. This is the stored trace,
> not a redrawing. Read the `caused_by` column down. Entry one measures. Entry two decides on
> that measurement — glare over text, retake. Entry three acts on that decision and opens a
> successor capture. Entry four is the beat this project exists for: compare captures. Glare
> over text, zero point nine two, to zero. Status, fixed. Then entry six fires a different rule
> off different metrics: edge touched at the bottom, text in the bottom band. That second
> instruction was not scripted. A different rule produced it, because the image measured
> differently.

**Do not say.** Do not read `SPEC.md` § 7's illustrative numbers (`0.34`, `hint_box
[412, 880, 760, 96]`) — they **do not match the shipped code**. Only the numbers on screen.

### Beat 5 — The human gate (2:35–3:19) · 44 s

**Budget.** 80 spoken words = 32.0 s speech · 11 s action (cut to browser 2 s, reload 1 s, type
the note 3 s, click Approve and let the queue re-render 3 s, cut back to the terminal 2 s) ·
**1.0 s margin** in a 44 s beat. Both `curl`s are recalled from history and return in well under
a tenth of a second, so they are narrated over rather than budgeted.

**Shot.** Terminal B for `/pending`, cut to the browser (light mode), then back to Terminal B
for the trace.

**Type this** (recalled with `pending`):

```sh
curl -s http://127.0.0.1:8080/pending | .venv/bin/python -c 'import json,sys; [print(c["capture_id"], c["state"], c["review_reason"]) for c in json.load(sys.stdin)]'
```

**On screen you should see** — exactly one line, because exactly one capture escalated:

```
c_006 escalated not_a_document
```

**Then, in the browser** at `http://127.0.0.1:8080/review`: reload the page, type the note
**`checked by hand, not a receipt`** into the item's note field, and click **Approve**. The item
vanishes and the page's `id="empty"` paragraph — *"Nothing is waiting for review."* — appears in
its place. That button issues `POST /approve/c_006` with the body
`{"note": "checked by hand, not a receipt"}`, which `app/server.py`'s `_approve` handler turns
into `invoke("approve", {...}, "reviewer")` — the same chokepoint the agent's own tools go
through, with the actor changed.

**Then back in Terminal B** (recalled with `trace/c_006`):

```sh
curl -s http://127.0.0.1:8080/trace/c_006 | .venv/bin/python -c 'import json,sys; [print(r["seq"], r["actor"], r["action"], r["outputs"], "caused_by", r["caused_by"]) for r in json.load(sys.stdin)]'
```

**On screen you should see:**

```
1 agent inspect_capture {'phash': 'eae8a4f4d4d0f8ea', 'nearest_distance': 36} caused_by None
2 agent decide_capture {'outcome': 'escalate', 'rule_id': 'not_a_document', 'reason_code': 'not_a_document'} caused_by 1
3 agent escalate {'review_item': 'opened'} caused_by 2
4 reviewer approve {'state': 'accepted'} caused_by 3
```

Three `agent` entries, then one `reviewer` entry. That fourth line is the whole beat.

**Narration** (80 spoken words · 32.0 s):

> One capture is waiting for a person. The review lane is the same server and the same route —
> the Approve button posts to `/approve`, which calls the same `invoke` chokepoint with the
> actor set to `reviewer`. The agent does not get its own code path. I type a note, and approve.
> The queue empties. Here is that capture's trace afterwards: three agent entries, then entry
> four — actor, `reviewer`. A person moved it to accepted, and the trace says so.

**Two claims were cut from this beat and must not come back.** Both are true of the code and
**not demonstrable on the screen this beat puts up**, which the claim-to-evidence rule in
section 7 forbids:

1. *"`approve` is a human verb; calling it as the agent raises."* The guard is real —
   `src/secondlook/agent_loop.py` raises `PermissionError` — but **no HTTP route can trigger
   it**: `_route_post` exposes only `/inspect` and `/approve/<capture_id>`, and `_approve`
   hard-codes the `reviewer` actor. The exception never reaches the screen.
2. *"the loop is a no-op on an escalated capture."* A `process_capture` fact, invisible through
   the routes this script uses.

**Do not add a shot to prove them.** This beat's timing is derived from the narration above; the
fix is the cut, not a new shot. Neither claim has a row in section 7.

**Do not use `dup_a.jpg` for this beat.** There is no HTTP route for `resolve_duplicate`, and
`approve` refuses a suspected duplicate — verified: `POST /approve` on a duplicate returns
HTTP 409, `{"error": "... is a suspected duplicate; resolve_duplicate before approving"}`.

**Do not say.** Do **not** say "there is no agent path to accepted" unqualified — `clean_a` was
auto-accepted ninety seconds earlier on this same screen. That claim is absent from the
narration above; do not reintroduce it in any form.

### Beat 6 — Architecture (3:19–4:03) · 44 s

**Budget.** 90 spoken words = 36.0 s speech · 6 s action (three zoom transitions, about 2 s each
to settle before speaking over them) · **2.0 s margin** in a 44 s beat.

**Shot.** [`architecture.svg`](./architecture.svg) open in the browser, **light mode**. Its
viewBox is `0 0 4465.89 2483` — far too wide to be legible in one frame. **Zoom into three
bands, following the narration**: the two adapters on the left, then the `invoke` chokepoint in
the middle, then the dashed not-built nodes. Three zooms is what the 6 s action budget buys; a
fourth costs 2 s this beat does not have. The same caution applies to
[`agent-workflow.svg`](./agent-workflow.svg) (`0 0 4607.72 5350`) if the owner shows it instead.

**Type this:** nothing. This beat is the diagram and the voice.

**On screen you should see**, in the three zoom bands in order: the `Local host — make run` and
`AWS` subgraphs; the yellow-bordered
`agent_loop.invoke(tool, args, actor)` node with `PERC`, `POLICY` and `VERDICT` below it, the
`OpenCV 5 — opencv-python-headless==5.0.0.93` subgraph holding measurements 1 to 8, and
`policy.decide() — 11-rule cascade, first match wins`; then the dashed nodes — `Lambda Function
URL … BLOCKED`, `Amazon S3 … NOT BUILT`, `Amazon CloudWatch Logs … NOT WIRED`,
`overlay.py evidence image … NOT BUILT`, `index.html agent lane … NOT BUILT` — and the legend
that defines dashed as planned-not-built.

**Narration** (90 spoken words · 36.0 s):

> Two adapters over one loop. A local stdlib HTTP server, and a Lambda container image on arm64
> behind a Function URL. Neither adapter holds decision logic. Inside, one chokepoint: `invoke`
> — a tool, its arguments, and an actor. Perception runs eight OpenCV 5 measurements. Policy
> walks an eleven-rule cascade, first match wins, from a committed threshold table. No model, no
> randomness. Everything dashed is not built: S3, CloudWatch, the evidence overlay, the
> agent-lane UI. Nothing is deployed, so the Function URL edge is dashed too. Everything you
> just saw ran locally.

**Do not say.** No live endpoint and no URL. The deploy was attempted and is blocked by the
account's Free Plan Service Control Policy, not merely unbuilt (`docs/deploy.md`). **"The Lambda
image is built and smoke-tested locally"** is the true form of that claim, and "everything you
just saw ran locally" is the form used above.

### Beat 7 — Principal results (4:03–4:28) · 25 s

**Budget.** 52 spoken words = 20.8 s speech · 3 s action (zoom to the table and let it settle) ·
**1.2 s margin** in a 25 s beat.

**Shot.** [`evaluation.md`](./evaluation.md)'s **Headline metrics** table on screen, zoomed so
the Value column is legible.

**Type this:** nothing. This beat is the table and the voice.

**On screen you should see** the rows the narration names: `Task-success rate` **15/15
(100.0%)**, **`Silent-accept rate`** **0/15 (0.0%)**, and `Escalation precision` **4/4
(100.0%)** — plus the section header naming the set: 17 samples, seed `20260908`,
`opencv-python-headless 5.0.0`.

**Narration** (52 spoken words · 20.8 s):

> Seventeen synthetic samples, fixed seed. Fifteen of fifteen with ground truth reach the right
> verdict. The number that matters is the silent-accept rate: zero. Not one bad capture was
> quietly accepted. Escalation precision is four of four — and that is trivially a hundred
> percent, because every escalated fixture is bad by construction.

**Do not say.** Do **not** quote the approval-latency figures (p50 55.0 ms). They come from a
scripted `time.sleep` gap in the evaluation harness, not from a human, and quoting them round
would misrepresent the entry. Escalation precision may only be spoken **with** its caveat
attached, exactly as written above.

---

## 6. Traps that ruin the take

| # | Trap | What goes wrong | The rule |
|---|---|---|---|
| 1 | Sample order | `clean_a.jpg` posted first makes `glare_text.jpg` return escalate / `suspected_duplicate` at `nearest_distance = 4`. The hook beat is destroyed. | Defects (`glare_text`, `crop_bottom`) **before** `clean_a`. |
| 2 | Wrong escalation sample | `dup_a.jpg` cannot be approved over HTTP — HTTP 409, and `resolve_duplicate` has no route. | Use `not_doc.jpg` for the approval beat. |
| 3 | Dark mode | `review.html` hardcodes `color: #1a1a1a` with no body background; in a dark-scheme viewer it renders dark-on-dark and looks broken. | Browser **and** OS in light mode before recording. |
| 4 | `SPEC.md` § 7 | Its demo script is aspirational — drop zone, evidence overlay, verdict panel, agent lane, side-by-side pages, **none built** — and its numbers are illustrative. | Narrate only what is on screen; use the real numbers. |
| 5 | No live endpoint | Deploy was attempted and is **blocked** by the only available AWS account's Free Plan Service Control Policy (`docs/deploy.md`), not merely unfinished. | Say "runs locally" / "built and smoke-tested locally". Never claim a deployed URL. If asked, the honest line is "deployment is blocked by an account restriction, documented in `docs/deploy.md`", not "not done yet". |
| 6 | Uncaveated metrics | Escalation precision is trivially 100 %; approval latency is simulated. | Caveat the first; do not speak the second. |
| 7 | `curl -w` into a JSON pipe | `-w` writes after the body on stdout, so the selector dies with `JSONDecodeError: Extra data: line 2 column 1`. | Use `-w '%{stderr}…'` so the timing goes to stderr and stdout stays pure JSON. |
| 8 | Rehearsal POSTs count | Pre-loading shell history runs the four `/inspect` calls for real and advances the capture ids, so the take would start at `c_007`. | Pre-load history **first**, then restart `make run`, then record. |

---

## 7. Claim-to-evidence map

One row per narrated claim. **If a claim has no third column, cut the claim — do not soften it.**

| Claim | Beat | Proof on screen |
|---|---|---|
| Glare over 92 % of the text, against a threshold of 15 % | 1 | S1's line reading `glare_over_text_frac 0.9211 \| threshold 0.15`, plus the `glare_over_total` rule id on the line above. The `0.15` is typed into the command the viewer watches run; its source is `src/secondlook/policy.toml`'s `glare_over_total` clause |
| OpenCV 5 answers, with these measurements | 1 | the measurement line S1 prints is OpenCV's own output for the image just posted. The version itself comes into shot in beat 6 as the diagram's `OpenCV 5 — opencv-python-headless==5.0.0.93` subgraph label — see the note below this table |
| A hint box on the failing region | 1 | `hint_box [201, 1006, 462, 141]` on the verdict line |
| Round trip well under a second | 1 | the `round trip 0.0…s` line that `curl -w '%{stderr}…'` prints to the terminal |
| A different metric fires a different rule | 3 | S3's `edge_touch_sides ['bottom']` and `bottom_band_has_text True`, next to rule id `bottom_edge_clipped` |
| A clean capture is accepted with no hint box | 3 | `c_005 accepted`, `accept accept None`, and its reason text |
| Not-a-receipt escalates rather than guessing | 3 | `quad_found False` next to `c_006 escalated` / `not_a_document` |
| Retake slots are opened by the agent | 3 | the id sequence across beats 1 and 3 — `c_001`, `c_003`, `c_005`, `c_006`; `c_002` and `c_004` never appear because the agent already took them |
| The driver's numbering restarts, so its ids differ | 4 | `run_demo.py` prints `'successor_id': 'c_002'` at seq 3 and `'successor_id': 'c_003'` at seq 7, against the server's `c_001`/`c_003`/`c_005`/`c_006` still visible in scrollback |
| The glare was fixed and a different defect took over | 4 | seq 4, `compare_captures … 'before': 0.9211` → `{'after': 0.0, 'status': 'fixed'}`, then seq 6's different rule |
| The decision caused the next call | 4 | the `caused_by` column, chaining 1 → 2 → 3 → 4 → 5 → 6 → 7 |
| One capture waits for a person | 5 | `GET /pending` through S5a prints exactly one line, `c_006 escalated not_a_document` |
| Approve runs through the same chokepoint as the agent | 5 | the button issues `POST /approve/c_006`; the trace then carries a `reviewer approve` entry that no other route could have written |
| A human, not the agent, moved it to accepted | 5 | `4 reviewer approve {'state': 'accepted'} caused_by 3` |
| Two adapters, one loop, one chokepoint | 6 | `architecture.svg`'s `Local host` and `AWS` subgraphs feeding the single `agent_loop.invoke(tool, args, actor)` node |
| Eight OpenCV 5 measurements | 6 | the diagram's `OpenCV 5` subgraph, nodes `1 · localise + rectify` through `8 · duplicate` |
| An eleven-rule cascade from a committed threshold table | 6 | the diagram's `policy.decide() — 11-rule cascade, first match wins` node — see the note below this table |
| Not built / not deployed | 6 | the dashed nodes and the legend in the same diagram |
| 15/15 correct verdicts, silent-accept rate 0 | 7 | `evaluation.md`'s Headline metrics table |
| Escalation precision 4/4, trivially so | 7 | the same table plus its stated caveat |

**Two rows above are architecture-level framing rather than shot-by-shot evidence, and are
marked as such rather than left silently uncovered.** Beat 1's "OpenCV 5" and beat 6's
"committed threshold table" name *where* the numbers come from, not a number on screen at that
instant. Each is covered on the delivered timeline by beat 6's diagram — the `OpenCV 5 —
opencv-python-headless==5.0.0.93` subgraph label, and the `11-rule cascade, first match wins`
node — and each is grounded in a committed file the judge can open: the pin in `README.md` and
`requirements.lock`, and the table at `src/secondlook/policy.toml` whose
`glare_over_text_frac > 0.15` clause is the very rule beat 1 fired. Neither is a claim about
something happening off screen; both are labels on the thing the viewer is already looking at.

Two beat-5 claims were **cut** under the rule at the top of this section — the agent-calls-
`approve` `PermissionError`, and the loop's no-op on an escalated capture. Both are code facts
with no route that puts them on screen. **Neither has a row here, and neither may be re-added to
the narration without first earning one.**

---

## 8. Dry run

**Date:** 8 September 2026. **Environment:** Python 3.13.13, `opencv-python-headless` 5.0.0,
curl 8.7.1, macOS on x86_64. **Server:** a single `make run` process, started clean —
`GET /health` returned `{"status": "ok"}` and `GET /pending` returned `[]` before the first POST.

The run was done twice against two separate fresh server processes: once to capture the output
that fills section 5's blocks, and once more — from a restarted `make run`, driven only by this
finished file, read top to bottom — to prove it is followable. On the second pass **every
command in section 5 was executed in the order written, with no step skipped, no step added,
and no decision left to the operator.** Both passes produced identical output but for the live
`round trip` figure. The "On screen you should see" blocks throughout section 5 are that
stdout, pasted verbatim; they are the transcript, distributed through the file rather than
repeated here.

Two mechanical substitutions were made, and neither changes what is executed. The seven
commands were run as literal command text rather than recalled with `Ctrl-R`, because recall
reproduces exactly that text — the recall step is a stopwatch optimisation for the presenter,
not a different call. And beat 5's Approve button was exercised by issuing its request
directly, `POST /approve/c_006` with `{"note": "checked by hand, not a receipt"}`, which is the
one call the button's own `fetch` makes; `app/server.py`'s `_approve` handler turns it into
`invoke("approve", {...}, "reviewer")` either way, so the mechanism under test is identical.

| What was checked | Result |
|---|---|
| Capture ids, in order | `c_001`, `c_003`, `c_005`, `c_006` — matching section 4's table exactly |
| Beat 1 round trip | `round trip 0.060270s`, and `0.061311s` on a second pass — the basis for "well under a second", and for the ban on any millisecond figure |
| Beat 1 metric | `glare_over_text_frac 0.9211` against the `0.15` threshold in `policy.toml` |
| Beat 3 verdicts | `bottom_edge_clipped` retake, `accept`, `not_a_document` escalate |
| Beat 4 runtime | `tools/run_demo.py` completed in **0.33 s** |
| Beat 4 output shape | **26 lines**, trace block on lines 4–12, **longest line 207 characters** — the source of the 30-row / 210-column direction in section 3 |
| Beat 4 successor ids | `'successor_id': 'c_002'` at seq 3 and `'successor_id': 'c_003'` at seq 7 — two different values, which is why the narration explains the restart |
| Review page | `GET /review` and `GET /` both returned HTTP 200, 3331 bytes of `text/html`, byte-identical to `app/static/review.html` |
| The approval | `POST /approve/c_006` with `{"note": "checked by hand, not a receipt"}` — the exact request the Approve button issues — returned `c_006 accepted` |
| The queue after approval | `GET /pending` returned no rows, which is the state the page renders as *"Nothing is waiting for review."* |
| The trace after approval | four entries, ending `4 reviewer approve {'state': 'accepted'} caused_by 3` |
| Repository afterwards | clean — uploads go to a per-process temp directory that `server_close` removes, so no capture file is left behind |

**What the dry run did not measure, stated plainly:** spoken delivery time. The run was driven
by tooling, so nothing was read aloud and no stopwatch ran. Every duration in section 1 is
derived arithmetically from a counted word total at 2.5 words/s plus itemised action seconds
plus margin — a budget, not a measurement. **The owner closes that gap with the read-aloud
rehearsal in the checklist below**, which is the last item before the recorder starts: if a beat
overruns its row, trim that beat's narration and re-count it, or raise its duration and re-check
that the seven still sum to 270 s or less. Never resolve an overrun by speaking faster than
2.5 words/s.

---

## 9. Narration, continuous

The seven blocks above, back to back, for a teleprompter. This text is word-for-word identical
to the per-beat blocks in section 5; if the two ever disagree, section 5 is the source.

> A receipt photographed under a window. Finance finds out it is unreadable at month end — days
> later, when the paper is already in a bin. Second Look measures the photo at capture instead.
> One POST, and OpenCV 5 answers: glare over ninety-two percent of the text against a threshold
> of fifteen, a hint box on the failing region, and an instruction — move the light behind you,
> shoot again. Round trip, well under a second.
>
> I'm Chetan Gupta. Second Look is a solo entry for the OpenCV AI Competition 2026, Agentic
> Vision track. The expensive thing here isn't OCR — it's the latency between a bad capture and
> anyone knowing it was bad, because that latency is what makes the defect permanent.
>
> Same endpoint, three more inputs from the committed synthetic set. A receipt with its bottom
> edge out of frame: different metrics fire — the frame edge is touched at the bottom, and there
> is text at the cut — so a different rule and a different instruction: step back, include the
> total line. A clean capture: accepted, no hint box. And something that is not a receipt: no
> document quad found, so the agent does not guess. It escalates. Notice the ids skip. Two of
> them are retake slots the agent already opened.
>
> This driver runs in its own process, so capture numbering restarts. This is the stored trace,
> not a redrawing. Read the `caused_by` column down. Entry one measures. Entry two decides on
> that measurement — glare over text, retake. Entry three acts on that decision and opens a
> successor capture. Entry four is the beat this project exists for: compare captures. Glare
> over text, zero point nine two, to zero. Status, fixed. Then entry six fires a different rule
> off different metrics: edge touched at the bottom, text in the bottom band. That second
> instruction was not scripted. A different rule produced it, because the image measured
> differently.
>
> One capture is waiting for a person. The review lane is the same server and the same route —
> the Approve button posts to `/approve`, which calls the same `invoke` chokepoint with the
> actor set to `reviewer`. The agent does not get its own code path. I type a note, and approve.
> The queue empties. Here is that capture's trace afterwards: three agent entries, then entry
> four — actor, `reviewer`. A person moved it to accepted, and the trace says so.
>
> Two adapters over one loop. A local stdlib HTTP server, and a Lambda container image on arm64
> behind a Function URL. Neither adapter holds decision logic. Inside, one chokepoint: `invoke`
> — a tool, its arguments, and an actor. Perception runs eight OpenCV 5 measurements. Policy
> walks an eleven-rule cascade, first match wins, from a committed threshold table. No model, no
> randomness. Everything dashed is not built: S3, CloudWatch, the evidence overlay, the
> agent-lane UI. Nothing is deployed, so the Function URL edge is dashed too. Everything you
> just saw ran locally.
>
> Seventeen synthetic samples, fixed seed. Fifteen of fifteen with ground truth reach the right
> verdict. The number that matters is the silent-accept rate: zero. Not one bad capture was
> quietly accepted. Escalation precision is four of four — and that is trivially a hundred
> percent, because every escalated fixture is bad by construction.

---

## 10. Owner checklist before hitting Record

- [ ] OS **and** browser in **light mode** (trap 3)
- [ ] Terminal B sized to at least **210 columns × 30 rows**, font large enough that `0.9211`
      is legible at the delivery resolution
- [ ] Notifications silenced; no other tab, window or editor visible
- [ ] `cd entries/opencv && make setup` completed
- [ ] All **seven** on-camera commands from section 4 run once off camera so they are in shell
      history, then `clear` (trap 8)
- [ ] **After** pre-loading history, `make run` **restarted** so the take begins at `c_001`
      (trap 8)
- [ ] `curl -s http://127.0.0.1:8080/health` returns `{"status": "ok"}` and
      `curl -s http://127.0.0.1:8080/pending` returns `[]`, both off camera
- [ ] `http://127.0.0.1:8080/review` open in the browser and left alone until beat 5
- [ ] Read section 9 aloud once at performance pace, timing each beat against its row in
      section 1's table; if any beat overruns, fix the narration or the table before recording
- [ ] Record the take, following section 5 top to bottom — four `/inspect` POSTs, in order, and
      **no others** (trap 1, rule 3 of section 4)
- [ ] Play the take back and check the total is at or under **4:30**, and certainly under 5:00
- [ ] Upload public or unlisted, then paste the link into `docs/submission.md`'s Demo video row
      and into the Devpost form — **owner action, both**
