#!/usr/bin/env bash
# build-pages.sh <out-dir> — builds the static replay site (index.html, run.json, img/)
# into <out-dir>, which must be new or empty. The site is a replay of a real run of the
# agent loop recorded at build time by tools/build_replay.py; nothing runs in the browser.
set -euo pipefail
out="${1:?usage: build-pages.sh <out-dir>}"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
cd "$(dirname "${BASH_SOURCE[0]}")"
[ -x .venv/bin/python ] || make setup
.venv/bin/python tools/build_replay.py "$out"
