# Second Look — the real-photograph set (set R): protocol

**Status: not collected.** Every number in [`evaluation.md`](./evaluation.md) comes from the
synthetic set S. This file is the protocol a real set will follow, written down before any
photo is taken so the set cannot be shaped to flatter the results. The harness is ready for it:
once `data/real/manifest.json` exists, `.venv/bin/python -m eval.run_eval` scores the set and
adds a "Set R" section to the report, whatever it shows.

## What it measures

Set S has exact ground truth by construction, so it cannot say how the thresholds behave on real
paper, real phones and real light. Set R answers four questions against a person's label:

| Metric | Question |
|---|---|
| Outcome agreement | Does the loop's outcome (accept / retake / escalate) match the label? |
| **Silent-accept rate** | Of the photos a person says should not be accepted, how many did the loop accept? The headline, as in set S. |
| Unneeded retake rate | Of the photos a person would accept, how many did the loop send back? |
| False-escalation rate | Of the photos a person would accept, how many did the loop send to a person? |

The results are reported as they come out, including a silent accept if one happens.

## The photos

**30 photos** across the eight conditions below, at least three of each. More is better;
fewer than 20 is not worth reporting as a rate.

| Condition | How to shoot it | Photos | Label a person would give |
|---|---|---|---|
| Clean | receipt flat on a contrasting surface, even light, whole receipt in frame | 6 | accept |
| Glare across the text | a window or lamp reflected on the printed lines, especially the total | 4 | retake |
| Glare on blank paper only | the reflection on the empty tail of the receipt, text clear | 3 | accept |
| Out of focus | phone focused on the table, or moving | 4 | retake |
| Bottom cropped | the total line or the bottom edge outside the frame | 4 | retake |
| Too dark / blown out | a dim room, or the flash at close range | 3 | retake |
| Two receipts in one frame | side by side | 3 | escalate |
| Not a receipt | a desk, a hand, a screen | 3 | escalate |

The duplicate check needs pairs in one batch, which this per-photo harness does not model; it
stays covered by set S.

- **Devices:** at least two phones if available, noted per photo (`device` field).
- **Receipts:** the owner's own receipts only. Photographs of a screen showing a receipt are a
  known undetected case (report § 7) and belong in "Not a receipt" only if labelled that way.
- **Format:** JPEG straight from the camera, no editing beyond the masking below, under 4 MB.

## Consent, privacy and licence

- **Only the owner's own receipts and surroundings.** No other person's receipt, face, name or
  hand in frame. No photo of anyone else's documents, even with permission, so no third-party
  consent is ever needed.
- **Mask before commit.** Card numbers (even the last four digits), card holder names,
  authorisation codes, loyalty numbers, the owner's address and any QR or barcode that encodes
  a transaction are covered with a solid black box before the photo is committed. Store names
  and prices may stay. Masking changes the text coverage slightly; that is accepted and noted.
- **Nothing identifying in the metadata.** Strip EXIF (location, device serial) before commit.
- **Licence:** the owner releases the committed photos under the same MIT licence as
  `data/synthetic/`, stated in `data/real/LICENSE` and in the manifest's `licence` field.
- **Alternative:** a CORD subset (<https://github.com/clovaai/cord>, CC BY 4.0) with attribution.
  CORD images are scanned receipts, not phone captures in bad light, so they test the accept
  side far better than the retake side; if used, report them as their own set, not mixed in.

## Labels and layout

```
data/real/
  LICENSE
  manifest.json
  r001.jpg ... r030.jpg
```

```json
{
  "licence": "MIT, photographed by the repository owner",
  "consent": "owner's own receipts only; card numbers, names and codes masked; EXIF stripped",
  "samples": [
    {"id": "r001", "file": "r001.jpg", "label": "accept", "defect": "clean",
     "device": "phone A", "notes": ""}
  ]
}
```

`label` is one of `accept`, `retake`, `escalate`: the outcome a person looking at the photo
says it deserves, decided **before** running the harness and not changed afterwards. `defect`
is the condition from the table above. Labelling is done by the owner looking at each photo;
where the call is genuinely unclear, the label is `escalate`, because that is what the policy's
uncertain band is for.
