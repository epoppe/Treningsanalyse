#!/usr/bin/env bash
# Linux/macOS smoke for desktop runtime pieces (repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TEST_DIR"; kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true; }
trap cleanup EXIT

echo "== Desktop smoke (AppData + health) =="
export TRAININGSANALYSE_DATA_DIR="$TEST_DIR"
export SKIP_GARMIN_INIT=true
export PYTHONPATH="$ROOT/backend"

"$ROOT/backend/.venv/bin/python" -m app.desktop_backend --host 127.0.0.1 --port 19876 &
BACK_PID=$!
for _ in $(seq 1 30); do
  curl -sf http://127.0.0.1:19876/health/live >/dev/null && break
  sleep 1
done
curl -sf http://127.0.0.1:19876/health/live | grep -q '"status":"ok"'
curl -sf http://127.0.0.1:19876/health/ready >/dev/null
test -f "$TEST_DIR/data/treningsanalyse.db"
echo "Backend OK → $TEST_DIR"

FRONTEND="$ROOT/dist/desktop/frontend"
if [[ -f "$FRONTEND/server.js" ]]; then
  echo "== Next standalone via ELECTRON_RUN_AS_NODE =="
  ELECTRON_RUN_AS_NODE=1 PORT=19877 HOSTNAME=127.0.0.1 DESKTOP_RUNTIME_PROXY=1 \
    "$ROOT/desktop/node_modules/.bin/electron" "$FRONTEND/server.js" &
  FRONT_PID=$!
  for _ in $(seq 1 30); do
    curl -sf http://127.0.0.1:19877/ >/dev/null && break
    sleep 1
  done
  curl -sf http://127.0.0.1:19877/ >/dev/null
  echo "Frontend OK"
else
  echo "Skip frontend smoke — run npm run desktop:prepare first"
fi

echo "Desktop smoke passed"
