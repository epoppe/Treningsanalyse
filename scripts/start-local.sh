#!/usr/bin/env bash
# Portable local start: backend (no reload) + frontend (next start after build).
# Usage: ./scripts/start-local.sh [--build]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD=0
if [[ "${1:-}" == "--build" ]]; then
  BUILD=1
fi

export SKIP_GARMIN_INIT="${SKIP_GARMIN_INIT:-true}"
export REDIS_ENABLED="${REDIS_ENABLED:-false}"
export ENVIRONMENT="${ENVIRONMENT:-local}"

BACKEND_PY="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$BACKEND_PY" ]]; then
  echo "Missing backend venv at backend/.venv — create it first:" >&2
  echo "  cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if [[ "$BUILD" -eq 1 ]] || [[ ! -d "$ROOT/frontend/.next" ]]; then
  echo "Building frontend…"
  npm run build --prefix "$ROOT/frontend"
fi

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

echo "Starting backend on :8000 (SKIP_GARMIN_INIT=$SKIP_GARMIN_INIT)…"
(
  cd "$ROOT/backend"
  SKIP_GARMIN_INIT="$SKIP_GARMIN_INIT" REDIS_ENABLED="$REDIS_ENABLED" ENVIRONMENT="$ENVIRONMENT" \
    "$BACKEND_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

echo "Waiting for /health/live…"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:8000/health/live" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
curl -fsS "http://127.0.0.1:8000/health/live" >/dev/null

echo "Starting frontend on :3000…"
(
  cd "$ROOT/frontend"
  npm run start -- --hostname 127.0.0.1 --port 3000
) &
FRONTEND_PID=$!

echo "Treningsanalyse lokal server:"
echo "  UI  http://127.0.0.1:3000"
echo "  API http://127.0.0.1:8000/health/ready"
wait
