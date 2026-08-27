#!/usr/bin/env bash
# Verify Electron win-unpacked layout and smoke the packaged backend.
# Run from repo root after: electron-builder --dir
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNPACKED="${1:-$ROOT/desktop/release/win-unpacked}"
RESOURCES="$UNPACKED/resources"

BACKEND_EXE="$RESOURCES/backend/treningsanalyse-backend/treningsanalyse-backend.exe"
FRONTEND_SERVER="$RESOURCES/frontend/server.js"
NODE_EXE="$RESOURCES/frontend/node.exe"

echo "== Packaged layout check =="
echo "Unpacked: $UNPACKED"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$UNPACKED" ]] || fail "Missing unpacked app: $UNPACKED"
[[ -f "$BACKEND_EXE" ]] || fail "Missing backend exe (expected COLLECT layout):\n  $BACKEND_EXE"
[[ -f "$FRONTEND_SERVER" ]] || fail "Missing frontend server:\n  $FRONTEND_SERVER"
[[ -f "$NODE_EXE" ]] || fail "Missing bundled node.exe:\n  $NODE_EXE"

# Flat layout must NOT be the only backend (would break Electron paths.ts)
FLAT="$RESOURCES/backend/treningsanalyse-backend.exe"
if [[ -f "$FLAT" && ! -f "$BACKEND_EXE" ]]; then
  fail "Backend is flat under resources/backend/ — COLLECT folder missing"
fi

echo "OK backend:  $BACKEND_EXE"
echo "OK frontend: $FRONTEND_SERVER"
echo "OK node:     $NODE_EXE"

echo "== Packaged backend /health/live smoke =="
TEST_DIR="$(mktemp -d)"
PORT=18765
cleanup() {
  if [[ -n "${BACK_PID:-}" ]]; then
    kill "$BACK_PID" 2>/dev/null || true
    wait "$BACK_PID" 2>/dev/null || true
  fi
  rm -rf "$TEST_DIR"
}
trap cleanup EXIT

# On Windows GitHub Actions this script runs under bash (Git Bash / MSYS).
export TRAININGSANALYSE_DATA_DIR="$TEST_DIR"
export SKIP_GARMIN_INIT=true
export DESKTOP_MODE=true

"$BACKEND_EXE" --host 127.0.0.1 --port "$PORT" &
BACK_PID=$!

for _ in $(seq 1 60); do
  if ! kill -0 "$BACK_PID" 2>/dev/null; then
    fail "Packaged backend exited before becoming healthy (pid=$BACK_PID)"
  fi
  if curl -sf "http://127.0.0.1:${PORT}/health/live" >/dev/null 2>&1; then
    echo "OK /health/live → HTTP 200"
    exit 0
  fi
  sleep 1
done

fail "Timed out waiting for packaged backend /health/live on port $PORT"
