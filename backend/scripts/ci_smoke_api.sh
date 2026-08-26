#!/usr/bin/env bash
# Smoke-test av FastAPI (brukes i GitHub Actions).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PORT="${SMOKE_PORT:-8010}"
HOST="${SMOKE_HOST:-127.0.0.1}"
BASE_URL="http://${HOST}:${PORT}"
PY="${BACKEND_DIR}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="${PYTHON:-python3}"
fi

cd "$BACKEND_DIR"

TMP_DB="$(mktemp /tmp/treningsanalyse-smoke-XXXXXX.db)"
trap 'kill "$SERVER_PID" >/dev/null 2>&1 || true; rm -f "$TMP_DB"' EXIT

export SKIP_GARMIN_INIT=true
export DATABASE_URL="sqlite:///${TMP_DB}"
export PYTHONPATH="$BACKEND_DIR"

echo "Starter API for smoke-test (db=$TMP_DB)..."
"$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT" >/tmp/ci_smoke_uvicorn.log 2>&1 &
SERVER_PID=$!

echo "Venter på API..."
for _ in $(seq 1 45); do
  if curl -sf "$BASE_URL/" >/dev/null; then
    break
  fi
  sleep 1
done

ROOT_HTTP="$(curl -s -o /tmp/ci_smoke_root.json -w "%{http_code}" "$BASE_URL/")"
OPENAPI_HTTP="$(curl -s -o /tmp/ci_smoke_openapi.json -w "%{http_code}" "$BASE_URL/openapi.json")"
HEALTH_HTTP="$(curl -s -o /tmp/ci_smoke_health.json -w "%{http_code}" "$BASE_URL/health")"
LIVE_HTTP="$(curl -s -o /tmp/ci_smoke_live.json -w "%{http_code}" "$BASE_URL/health/live")"
READY_HTTP="$(curl -s -o /tmp/ci_smoke_ready.json -w "%{http_code}" "$BASE_URL/health/ready")"

if [[ "$ROOT_HTTP" != "200" || "$OPENAPI_HTTP" != "200" || "$HEALTH_HTTP" != "200" || "$LIVE_HTTP" != "200" ]]; then
  echo "NO-GO: smoke feilet (root=$ROOT_HTTP openapi=$OPENAPI_HTTP health=$HEALTH_HTTP live=$LIVE_HTTP)"
  cat /tmp/ci_smoke_uvicorn.log || true
  exit 1
fi

if [[ "$READY_HTTP" != "200" && "$READY_HTTP" != "503" ]]; then
  echo "NO-GO: /health/ready forventet 200 eller 503, fikk $READY_HTTP"
  cat /tmp/ci_smoke_ready.json || true
  cat /tmp/ci_smoke_uvicorn.log || true
  exit 1
fi

SCHEMA_OK="$("$PY" - <<'PY'
import json
data = json.load(open("/tmp/ci_smoke_health.json"))
print("true" if data.get("schema_at_head") and data.get("schema_version") else "false")
PY
)"

if [[ "$SCHEMA_OK" != "true" ]]; then
  echo "NO-GO: /health mangler gyldig schema_version"
  cat /tmp/ci_smoke_health.json
  exit 1
fi

echo "GO: API smoke OK (schema=$(jq -r .schema_version /tmp/ci_smoke_health.json 2>/dev/null || cat /tmp/ci_smoke_health.json))"
