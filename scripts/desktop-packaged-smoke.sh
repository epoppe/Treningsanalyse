#!/usr/bin/env bash
# Verify Electron win-unpacked layout and smoke the packaged backend.
# Run from repo root after: electron-builder --dir
#
# Critical: the package tree is made read-only so import-time mkdir under
# Program Files / resources cannot silently succeed (as it did on writable CI).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNPACKED="${1:-$ROOT/desktop/release/win-unpacked}"
RESOURCES="$UNPACKED/resources"
BACKEND_DIR="$RESOURCES/backend/treningsanalyse-backend"
BACKEND_EXE="$BACKEND_DIR/treningsanalyse-backend.exe"
FRONTEND_SERVER="$RESOURCES/frontend/server.js"
NODE_EXE="$RESOURCES/frontend/node.exe"

echo "== Packaged layout check =="
echo "Unpacked: $UNPACKED"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$UNPACKED" ]] || fail "Missing unpacked app: $UNPACKED"
[[ -f "$BACKEND_EXE" ]] || fail "Missing backend exe (expected COLLECT layout):\n  $BACKEND_EXE"
[[ -f "$FRONTEND_SERVER" ]] || fail "Missing frontend server:\n  $FRONTEND_SERVER"
[[ -f "$NODE_EXE" ]] || fail "Missing bundled node.exe:\n  $NODE_EXE"

FLAT="$RESOURCES/backend/treningsanalyse-backend.exe"
if [[ -f "$FLAT" && ! -f "$BACKEND_EXE" ]]; then
  fail "Backend is flat under resources/backend/ — COLLECT folder missing"
fi

echo "OK backend:  $BACKEND_EXE"
echo "OK frontend: $FRONTEND_SERVER"
echo "OK node:     $NODE_EXE"

# Snapshot package tree before launch (detect pollution)
PACKAGE_SNAPSHOT="$(mktemp)"
( cd "$BACKEND_DIR" && find . -print | sort > "$PACKAGE_SNAPSHOT" )

echo "== Make package backend tree read-only (simulate Program Files) =="
# Keep execute bit on the exe; strip write from files/dirs under COLLECT.
if command -v chmod >/dev/null 2>&1; then
  find "$BACKEND_DIR" -type d -exec chmod a-w {} + 2>/dev/null || true
  find "$BACKEND_DIR" -type f -exec chmod a-w {} + 2>/dev/null || true
  chmod u+rx "$BACKEND_EXE" 2>/dev/null || chmod a+rx "$BACKEND_EXE" 2>/dev/null || true
fi

echo "== Packaged backend /health/live smoke =="
TEST_DIR="$(mktemp -d)"
PORT=18765
BACK_PID=""

restore_package_perms() {
  if command -v chmod >/dev/null 2>&1; then
    find "$BACKEND_DIR" -type d -exec chmod u+rwx {} + 2>/dev/null || true
    find "$BACKEND_DIR" -type f -exec chmod u+rw {} + 2>/dev/null || true
  fi
}

cleanup() {
  if [[ -n "${BACK_PID}" ]]; then
    kill "$BACK_PID" 2>/dev/null || true
    wait "$BACK_PID" 2>/dev/null || true
  fi
  restore_package_perms
  rm -f "$PACKAGE_SNAPSHOT"
  rm -rf "$TEST_DIR"
}
trap cleanup EXIT

# Mirror Electron buildBackendEnv (mutable paths only under AppData-like root)
export TRAININGSANALYSE_DATA_DIR="$TEST_DIR"
export TOKEN_DIR="$TEST_DIR/tokens"
export DATA_DIR="$TEST_DIR/data"
export FIT_DATA_DIR="$TEST_DIR/fit"
export CACHE_DIR="$TEST_DIR/cache"
export LOG_DIR="$TEST_DIR/logs"
export BACKUP_DIR="$TEST_DIR/backups"
export SKIP_GARMIN_INIT=true
export DESKTOP_MODE=true
export DATABASE_URL="sqlite:///${TEST_DIR}/data/treningsanalyse.db"

# Normalize Windows path for sqlite URL when running under Git Bash
if [[ "$OSTYPE" == msys* ]] || [[ "$OSTYPE" == cygwin* ]] || [[ -n "${WINDIR:-}" ]]; then
  # Convert /c/Users/... → C:/Users/... for SQLAlchemy
  WIN_DB="$(cygpath -m "$TEST_DIR/data/treningsanalyse.db" 2>/dev/null || echo "$TEST_DIR/data/treningsanalyse.db")"
  export DATABASE_URL="sqlite:///${WIN_DB}"
  WIN_ROOT="$(cygpath -m "$TEST_DIR" 2>/dev/null || echo "$TEST_DIR")"
  export TRAININGSANALYSE_DATA_DIR="$WIN_ROOT"
  export TOKEN_DIR="$WIN_ROOT/tokens"
  export DATA_DIR="$WIN_ROOT/data"
  export FIT_DATA_DIR="$WIN_ROOT/fit"
  export CACHE_DIR="$WIN_ROOT/cache"
  export LOG_DIR="$WIN_ROOT/logs"
  export BACKUP_DIR="$WIN_ROOT/backups"
fi

"$BACKEND_EXE" --host 127.0.0.1 --port "$PORT" &
BACK_PID=$!

READY=0
for _ in $(seq 1 60); do
  if ! kill -0 "$BACK_PID" 2>/dev/null; then
    fail "Packaged backend exited before becoming healthy (pid=$BACK_PID). Likely wrote to read-only package tree."
  fi
  if curl -sf "http://127.0.0.1:${PORT}/health/live" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done
[[ "$READY" -eq 1 ]] || fail "Timed out waiting for packaged backend /health/live on port $PORT"
echo "OK /health/live → HTTP 200"

echo "== Assert mutable dirs only under AppData root =="
for sub in tokens data fit cache logs backups; do
  [[ -d "$TEST_DIR/$sub" ]] || fail "Expected writable dir missing: $TEST_DIR/$sub"
done
# DB created by Alembic under AppData
if [[ ! -f "$TEST_DIR/data/treningsanalyse.db" ]]; then
  # Windows path may differ slightly; accept any sqlite under data/
  ls "$TEST_DIR/data"/*.db >/dev/null 2>&1 || fail "Expected SQLite DB under $TEST_DIR/data"
fi

echo "== Assert package tree was not polluted =="
# Forbidden mutable names under COLLECT package
for bad in tokens data fit cache logs backups exports treningsanalyse.db; do
  if [[ -e "$BACKEND_DIR/$bad" ]]; then
    fail "Package pollution: $BACKEND_DIR/$bad must not exist (mutable data leaked into install dir)"
  fi
done

AFTER_SNAPSHOT="$(mktemp)"
( cd "$BACKEND_DIR" && find . -print | sort > "$AFTER_SNAPSHOT" )
if ! diff -q "$PACKAGE_SNAPSHOT" "$AFTER_SNAPSHOT" >/dev/null; then
  echo "Package tree changed during smoke:" >&2
  diff -u "$PACKAGE_SNAPSHOT" "$AFTER_SNAPSHOT" >&2 || true
  rm -f "$AFTER_SNAPSHOT"
  fail "Packaged backend modified files under resources/backend (must be read-only)"
fi
rm -f "$AFTER_SNAPSHOT"

echo "Packaged backend smoke passed (AppData-only writes, package unchanged)"
