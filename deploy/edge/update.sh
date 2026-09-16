#!/bin/bash
# Pull origin/$MARVIN_GIT_REF and rebuild the edge stack. Settings → Update and `make update` both run this.
# Runs in a sibling container (marvin-update), not the worker — compose will kill the worker mid-rebuild.
# .env is untracked and stays put. Writes /work/state/update.log + update.json so the page can show progress
# even while the worker is down.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
REF=${MARVIN_GIT_REF:-main}
STATE_DIR=${MARVIN_STATE_DIR:-/work/state}
OWNER=$(stat -c %u:%g "$ROOT" 2>/dev/null || stat -f %u:%g "$ROOT")
cd "$ROOT"
if ! mkdir -p "$STATE_DIR" 2>/dev/null || [ ! -w "$STATE_DIR" ]; then
  STATE_DIR=/tmp/marvin-update
  mkdir -p "$STATE_DIR"
fi
LOG=$STATE_DIR/update.log
STATE=$STATE_DIR/update.json
: > "$LOG"

note() { echo "$(date -Is) $*" | tee -a "$LOG"; }

write_state() {
  # $1 = step, $2 = applying (true/false), $3 = error or empty
  STEP=$1 APPLYING=$2 ERR=${3:-} python3 - "$STATE" <<'PY'
import json, os, sys, time
path = sys.argv[1]
try:
    cur = json.loads(open(path).read())
except Exception:
    cur = {}
cur["step"] = os.environ["STEP"]
cur["applying"] = os.environ["APPLYING"] == "true"
err = os.environ.get("ERR") or None
cur["error"] = err
sha = os.environ.get("MARVIN_GIT_SHA")
if sha:
    cur["sha"] = sha
if cur["applying"]:
    cur.setdefault("started_at", time.time())
    cur["finished_at"] = None
else:
    cur["finished_at"] = time.time()
open(path, "w").write(json.dumps(cur))
PY
}

fail() {
  note "FAILED: $*"
  write_state "failed" false "$*"
  exit 1
}
trap 'fail "update.sh exited ${BASH_COMMAND}"' ERR

write_state "fetching" true
note "updating $ROOT to origin/$REF"
git fetch --depth 50 origin "$REF"
git reset --hard "origin/$REF"
chown -R "$OWNER" "$ROOT" 2>/dev/null || true
export MARVIN_GIT_SHA
MARVIN_GIT_SHA=$(git rev-parse HEAD)
export MARVIN_INSTALL_DIR="$ROOT"
HARNESSES=${SANDBOX_HARNESSES:-claude-code grok}
IMAGE=${MARVIN_SANDBOX_IMAGE:-marvin-sandbox:local}

write_state "building sandbox" true
note "building sandbox $IMAGE (this is the long step)"
docker build --build-arg HARNESSES="$HARNESSES" -t "$IMAGE" "$ROOT/deploy/sandbox"

write_state "rebuilding stack" true
note "edge-up $MARVIN_GIT_SHA — worker will restart; that is expected"
docker compose -f "$ROOT/docker-compose.edge.yml" --project-directory "$ROOT" up -d --build

write_state "ready" false
note "ready $MARVIN_GIT_SHA"
