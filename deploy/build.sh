#!/usr/bin/env bash
# Builds the Lambda container image locally. No AWS call, no credential needed — this is
# the one step #46 itself may execute for real (see docs/deploy.md). deploy.sh calls this
# same script before it pushes, so the build path proven here is the one actually shipped.
set -euo pipefail

ENTRY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="${IMAGE_TAG:-secondlook-lambda:local}"
PLATFORM="${PLATFORM:-linux/arm64}"

cd "$ENTRY_ROOT"
tar --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
    --exclude='.ruff_cache' --exclude='data/synthetic' --exclude='*.pyc' \
    --exclude='.git' -cf - . \
  | docker build --platform "$PLATFORM" -f deploy/Dockerfile -t "$IMAGE_TAG" -

echo "built ${IMAGE_TAG} for ${PLATFORM}"
