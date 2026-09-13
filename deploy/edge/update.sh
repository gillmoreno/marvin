#!/bin/bash
# Pull origin/$MARVIN_GIT_REF and rebuild the edge stack. Settings → Update and `make update` both run this.
# .env is untracked and stays put. Rooms drop for the length of the image build.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
REF=${MARVIN_GIT_REF:-main}
OWNER=$(stat -c %u:%g "$ROOT" 2>/dev/null || stat -f %u:%g "$ROOT")
cd "$ROOT"
note() { echo "$(date -Is) $*"; }
note "updating $ROOT to origin/$REF"
git fetch --depth 50 origin "$REF"
git reset --hard "origin/$REF"
chown -R "$OWNER" "$ROOT" 2>/dev/null || true
export MARVIN_GIT_SHA
MARVIN_GIT_SHA=$(git rev-parse HEAD)
export MARVIN_INSTALL_DIR="$ROOT"
HARNESSES=${SANDBOX_HARNESSES:-claude-code grok}
IMAGE=${MARVIN_SANDBOX_IMAGE:-marvin-sandbox:local}
note "building sandbox $IMAGE"
docker build --build-arg HARNESSES="$HARNESSES" -t "$IMAGE" "$ROOT/deploy/sandbox"
note "edge-up $MARVIN_GIT_SHA"
docker compose -f "$ROOT/docker-compose.edge.yml" --project-directory "$ROOT" up -d --build
note "ready $MARVIN_GIT_SHA"
