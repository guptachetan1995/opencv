#!/usr/bin/env bash
# Verification for the opencv entry: the doc-stage structural checks from #43, then
# `ruff check`, `ruff format --check` and `pytest` (#44).
# Kept compatible with the bash 3.2 that ships on macOS: no mapfile, no negative
# array indices.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

fail() { echo "ERROR: $1" >&2; exit 1; }

echo "== entry root files =="
for f in SPEC.md README.md LICENSE; do
  [ -f "$f" ] || fail "$f is missing from the entry root"
  echo "  ok: $f"
done

echo "== LICENSE is MIT and visible =="
grep -q '^MIT License' LICENSE || fail "LICENSE is not the MIT licence text"

echo "== SPEC.md sections, in the order the spec fixes =="
expected=(
  "1. The customer confusion this entry resolves"
  "2. The concept"
  "3. What the agent does, what only the human does"
  "4. The perception layer"
  "5. Tool list"
  "6. Data model"
  "7. Demo script"
  "8. The decision layer"
  "9. Serving surface and AWS target"
  "10. Sample data and licences"
  "11. Stack pin"
  "12. File layout"
  "13. Test plan"
  "14. Evaluation plan"
  "15. Responsible use"
  "16. Diagram outlines"
  "17. Research sources"
  "18. Not in scope"
  "19. Submission checklist"
)
found=()
while IFS= read -r line; do
  found+=("$line")
done < <(grep -E '^## ' SPEC.md)

[ "${#found[@]}" -eq "${#expected[@]}" ] ||
  fail "SPEC.md has ${#found[@]} top-level sections, expected ${#expected[@]}"

i=0
while [ "$i" -lt "${#expected[@]}" ]; do
  case "${found[$i]}" in
    "## ${expected[$i]}"*) echo "  ok: ${expected[$i]}" ;;
    *) fail "section $((i + 1)) is '${found[$i]}', expected to start with '## ${expected[$i]}'" ;;
  esac
  i=$((i + 1))
done

echo "== the submission checklist is the final section =="
last="${found[$((${#found[@]} - 1))]}"
[ "$last" = "## 19. Submission checklist" ] ||
  fail "the last section of SPEC.md is '$last', not the submission checklist"

echo "== no unresolved placeholders =="
if grep -nE 'TODO|TBD' SPEC.md README.md; then
  fail "SPEC.md or README.md still contains a placeholder"
fi

echo "== the checklist covers every rule item =="
items=(
  "OpenCV 5 for substantive image or video analysis"
  "technical report"
  "judge-accessible code repository"
  "Pinned dependencies"
  "architecture diagram"
  "working web endpoint"
  "no more than five minutes"
  "failure cases"
  "perception-decision-action loop"
  "must change what the system does next"
  "agent workflow diagram"
  "changes a later decision"
  "Oct 26, 2026 @ 11:45pm PDT"
  "Agentic Vision"
)
for item in "${items[@]}"; do
  grep -qi -- "$item" SPEC.md || fail "the submission checklist does not mention: $item"
  echo "  ok: $item"
done

# The two facts a later goal is most likely to undo by accident. Both were decided from
# live sources on 8 Sep 2026 and both are load-bearing, so they are asserted, not trusted.
echo "== App Runner stays ruled out =="
grep -q 'AWS App Runner is ruled out and must not be reintroduced' SPEC.md ||
  fail "SPEC.md no longer carries the App Runner exclusion heading"
grep -q 'no longer accept new customers starting on April 30, 2026' SPEC.md ||
  fail "SPEC.md no longer cites the App Runner closure notice verbatim"
grep -q 'Lambda Function URL' SPEC.md ||
  fail "SPEC.md no longer names a Lambda Function URL as the serving surface"

echo "== OpenCV 5 pin is exact and OpenCV 5, not 4.x =="
grep -q 'opencv-python-headless==5.0.0.93' SPEC.md ||
  fail "SPEC.md no longer pins opencv-python-headless==5.0.0.93"
grep -q 'opencv-python-headless==5.0.0.93' README.md ||
  fail "README.md no longer pins opencv-python-headless==5.0.0.93"

echo "== Python project: lint, format, tests =="
# The root runner must pass from a fresh clone; make setup is idempotent and only installs
# once (it stamps .venv/.installed), so this costs nothing on a warm checkout.
[ -x .venv/bin/python ] && [ -f .venv/.installed ] || make setup
.venv/bin/ruff check . || fail "ruff check found problems"
.venv/bin/ruff format --check . || fail "ruff format --check found unformatted files"
.venv/bin/python -m pytest || fail "pytest failed"

echo "opencv: all checks passed."
