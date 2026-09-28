# Second Look — demo video script and shot list (the re-cut)

**Status: scripted, not yet rendered.** The published video, <https://youtu.be/zOfV23uB8Ts>
(4:28), was made from the earlier version of this file. This version is the re-cut: it opens
on the receipts instead of a terminal, shows the evidence overlay and the review page's new
controls, rejects the non-receipt instead of approving it, and shows the agent being refused.
It replaces the published link only once it has been rendered, checked and uploaded.

Every frame is either the entry's real running app or a real build of it, and every line of
terminal text is captured from a real run at render time — nothing on screen is typed by hand.
The render is a frame-exact slideshow: each shot's on-screen state is reached, screenshotted and
held for its exact duration, and the narration is synthesised per shot and padded to it.

## Changes from the published cut, and why

| Published cut | Re-cut | Why |
|---|---|---|
| Opened on 36 s of terminal; the title card came second | A title card with the team for the first 10 s, then the glare photo with its hint box | No receipt image appeared anywhere in the published cut, in a computer-vision competition |
| "glare over ninety-two percent of the text" | "ninety-two percent of the glare lies on the text lines" | `glare_over_text_frac` is the share of the *glare* that falls on the text lines (`metrics.glare`), not the share of the text under glare; the earlier line misread the metric |
| The review beat typed "checked by hand, not a receipt" and then clicked **Approve** | The reviewer **rejects** the non-receipt | Approving a capture the note calls "not a receipt" contradicted the evaluation, which resolves `not_doc` as reject |
| The review-page and results frames showed section references to an unpublished design file | Neither appears | Those references pointed at a file that is not in the repository; the review page and `evaluation.md` no longer carry them |
| No evidence overlay, one Approve button | The overlay, the clause that fired, Reject, and the reviewer token | The review lane is now a decision surface |
| Nothing showed the gate holding against the agent itself | An MCP-connected agent calling its tools on an escalated capture, every call refused | The human-gate claim now holds by construction and is shown, not asserted |
| 4:28 | 4:01 | Under the five-minute limit with room for a slower voice |

## Shot table

The render reads this table: one row per shot, in order, with its duration in milliseconds
(a whole number of 40 ms frames) and its narration, word for word. Each shot's narration must
fit its own duration, because the narration is padded or trimmed to its shot. The budget rule
from the earlier cut still holds: **duration ≥ spoken words ÷ 2.5 + 1 s**, counting a
hyphenated or numeric term as the words it takes to say.

| Beat | id | Duration (ms) | Narration |
|---|---|---|---|
| 1 | `title` | 10000 | Second Look: a solo entry by Chetan Gupta for the OpenCV AI Competition 2026, Agentic Vision track. |
| 2 | `glare` | 33000 | A receipt photographed under a window. Finance usually finds out it is unreadable at month end, when the paper is already in a bin. Second Look measures the photo at the moment of capture. OpenCV 5 finds the receipt and straightens it. Ninety-two percent of the glare lies on the text lines, against a threshold of fifteen percent, so the answer is retake, with a box on the region and one instruction: move the light behind you. |
| 3 | `retake` | 28000 | The retake arrives. Compare captures reports the glare fixed, from ninety-two percent to zero. But the new framing cut off the bottom of the receipt, with text at the cut. So a different rule fires, on a different metric, with a different box: step back and include the total line. Nothing scheduled that second instruction. The second photo's measurements chose it. |
| 4 | `http` | 26000 | The same chain runs over HTTP. Inspect returns the retake slot, the retake photo is posted into it, and a third photo is accepted. The stored trace links every call to the one that caused it: entry four, the glare fixed; entry six, a different rule; entry ten, accepted. |
| 5 | `review-open` | 19000 | Anything the agent should not decide goes to a person. This frame has no receipt in it, so the agent escalates instead of guessing. The reviewer sees what OpenCV saw: the photo, the regions it found, and the clause that fired. |
| 5 | `review-note` | 6000 | The reviewer adds a note and rejects it. |
| 5 | `review-done` | 12000 | These buttons call the same invoke chokepoint as the agent's tools, as the reviewer, and only with the reviewer's token. The queue is empty. |
| 6 | `gate` | 26000 | And an agent cannot route around the person. Here an agent connected over MCP calls its tools on an escalated capture: every one is refused, and approve is not even a tool it can see. Over HTTP, the review routes answer four-oh-one without the reviewer's token. |
| 7 | `arch-adapters` | 13000 | One loop, three thin adapters: a standard-library HTTP server, a Lambda handler, and an MCP server that offers the agent tools and never the human verbs. |
| 7 | `arch-core` | 16000 | Inside, one chokepoint with two guards: who is calling, and whether the capture is still the agent's to touch. Eight OpenCV 5 measurements, and an eleven-rule cascade from a committed table. No model decides. |
| 7 | `arch-aws` | 12000 | Dashed means not built or not deployed. The Lambda path is blocked by the account's policy, and an EC2 deploy is prepared for launch. |
| 8 | `results` | 30000 | Seventeen synthetic samples, fixed seed. One receipt at a time, fifteen of fifteen reach the right verdict. In one shared batch, nine of fifteen: receipts with the same layout collide as suspected duplicates, and every one of those goes to a person. Silent accepts, the number that matters, are zero both ways. There is no real-photo set yet; its protocol is written. |
| 9 | `close` | 10000 | The code, the report and the evaluation are at the link below. |

Total: 10 + 33 + 28 + 26 + 19 + 6 + 12 + 26 + 13 + 16 + 12 + 30 + 10 = **241 s = 4:01**, 59 s
under the 300 s limit. The rules' four required elements: the team (beat 1), the application
working (beats 2–6), its architecture (beat 7), its principal results (beat 8).

## What each shot shows

| id | On screen | Source |
|---|---|---|
| `title` | "Second Look" · "OpenCV AI Competition 2026 · Agentic Vision" · "Chetan Gupta — solo entry" | a card; the name is the repository's `LICENSE` byline |
| `glare` | scene 1 of the replay site: `glare_text.jpg`'s evidence overlay — the frame with its quad, the rectified page with the glare box and the red hint box, the header `RETAKE glare_over_total` / `glare_over_text_frac 0.92 > 0.15` / the instruction — and, beside it, the verdict and the trace | `./build-pages.sh`, a real run recorded at render time |
| `retake` | scene 2: `crop_bottom.jpg`'s overlay with the bottom-band hint box, `RETAKE bottom_edge_clipped`, and the trace whose entry 4 reads `compare_captures … {"after": 0.0, "status": "fixed"}` | the same build |
| `http` | a terminal: three `curl` calls against a freshly started `app/server.py` (`/inspect`, `/retake/c_002`, `/retake/c_003`) and `GET /trace/c_003`, ten entries | captured from the live server at render time |
| `review-open` | the review page after the reviewer token is entered: `not_doc.jpg`'s card with its overlay, the `not_a_document` clause table (`quad_found false == false`, fired) and its measurements | a second fresh server with one escalation posted |
| `review-note` | the same card with the note "not a receipt" typed | the same page |
| `review-done` | after **Reject**: "Nothing is waiting for review." | the same page |
| `gate` | a terminal: an MCP client session with `app/mcp_server.py` — `open_capture` and `run_loop` escalate `not_doc.jpg`, then each agent tool on it answers `StateError: … refused`, and `approve` answers `Unknown tool`; then `curl … /approve/c_004` answering `{"error": "reviewer token required"}` | captured at render time |
| `arch-*` | `docs/architecture.svg`, zoomed to the adapters, the chokepoint and the dashed AWS nodes | the committed diagram |
| `results` | the headline rows of `docs/evaluation.md`: 15/15 isolated, 9/15 shared batch, 0/15 silent accepts in both, 5/6 retake convergence, 4/4 escalation precision with its caveat | read from the committed file at render time |
| `close` | the repository URL, the Devpost page, and the screen-share offer | a card |

## Claims and where the screen proves them

| Claim | Shot | Proof on screen |
|---|---|---|
| OpenCV 5 finds the receipt and straightens it | `glare` | the overlay's "as posted" panel with the green quad beside the "rectified page" panel |
| 92% of the glare lies on the text lines, threshold 15% | `glare` | the overlay header `glare_over_text_frac 0.92 > 0.15` |
| A box on the region and one instruction | `glare` | the red hint box and the header's third line |
| The glare fixed, 92% to zero | `retake` | trace entry 4, `compare_captures`, `before 0.9211` → `after 0.0, fixed` |
| A different rule, a different metric, a different box | `retake` | `RETAKE bottom_edge_clipped`, `edge_touch_sides [bottom] contains bottom`, the bottom-band box |
| The same chain over HTTP; entry ten accepted | `http` | the three `curl` outputs and the ten-row trace |
| Escalates instead of guessing; the reviewer sees what OpenCV saw | `review-open` | `not_a_document`, the overlay, the fired clause |
| The reviewer rejects it; the queue empties | `review-note`, `review-done` | the note, then "Nothing is waiting for review." |
| Only with the reviewer's token | `review-open`, `gate` | the token field; the `401` body in the `gate` terminal |
| Every agent tool is refused on an escalated capture; approve is not a tool | `gate` | the `StateError` lines and `Unknown tool: approve` |
| Three adapters, one chokepoint, two guards, 8 measurements, 11 rules | `arch-*` | the diagram's nodes |
| Lambda blocked, EC2 prepared | `arch-aws` | the dashed nodes' labels |
| 15/15, 9/15, 0/15 both ways | `results` | the table |

**If the EC2 instance has been launched and verified before the render**, `arch-aws` is
stale: redraw the diagram with the EC2 node solid and change that line to "The Lambda path is
blocked by the account's policy; the same routes run on EC2." and nothing else.

## Recording notes

- The two servers are fresh processes on ports nothing else uses, started by the render and
  stopped after it: one for the `http` capture, one for the review shots, so the review page's
  capture is `c_001` and nothing from the `http` beat leaks into it.
- The reviewer token for the render is generated per run and typed into the page's password
  field, so it is never visible.
- The review page is recorded in the viewer's light colour scheme; it now also has a dark one.
- Buttons are selected by exact text (`button:text-is('Reject')`).
- Upload as **Public**. Title, description and tags come from `docs/submission.md`.
