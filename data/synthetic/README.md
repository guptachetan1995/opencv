# Synthetic sample set (SPEC § 10, primary set)

Seventeen 1200×1600 JPEG (q85) captures of three synthetic receipts on a textured table,
each with one defect applied by `tools/make_samples.py` through OpenCV with known
parameters. `manifest.json` is the ground truth: for every sample, the base receipt, the
defect, its exact parameters and the coordinate space they are in (`paper` = the flat
receipt before it was placed on the table, `frame` = the saved image), the four corners
the paper was placed at, and the verdict the committed policy is expected to reach
(`null` for samples that exist only for a monotonicity test).

Licence: MIT, ours — see `LICENSE` beside this file. Nothing here depicts a real business,
person, card or transaction; the shop names, addresses and card digits are invented.

Regenerate with `make samples` (seed `20260908`). On one platform the output is
byte-identical run to run. Across platforms the pinned Pillow and OpenCV wheels bundle
their own FreeType and libjpeg builds, so a regenerated image can differ from the
committed one by a few least-significant bits; `tests/test_samples.py` therefore asserts
the manifest is identical and the images agree within a mean absolute difference, not
byte equality.
