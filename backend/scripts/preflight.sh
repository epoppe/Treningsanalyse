#!/usr/bin/env bash
set -euo pipefail

# Preflight for Treningsanalyse backend
# Kjør fra repo-root: ./backend/scripts/preflight.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"
PORT="${PREFLIGHT_PORT:-8010}"
HOST="${PREFLIGHT_HOST:-127.0.0.1}"
BASE_URL="http://${HOST}:${PORT}"

echo "== Preflight: Treningsanalyse backend =="
echo "Repo: $ROOT_DIR"
echo "Backend: $BACKEND_DIR"
echo

cd "$BACKEND_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Oppretter virtualenv..."
  python3 -m venv .venv
fi

echo "Aktiverer virtualenv..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
PY="$VENV_DIR/bin/python"

echo "Installerer avhengigheter..."
pip install -r requirements.txt >/dev/null

echo "Sikrer parquet-engine (pyarrow)..."
pip install pyarrow >/dev/null

if [[ ! -f ".env" ]]; then
  echo "Advarsel: backend/.env mangler. Oppretter fra env.example."
  cp env.example .env
  echo "Fyll inn GARMIN_EMAIL/GARMIN_PASSWORD i backend/.env før real-mode kjøring."
fi

echo "Kompilerer kritiske Python-filer..."
python3 -m py_compile \
  "$BACKEND_DIR/app/config.py" \
  "$BACKEND_DIR/app/main.py" \
  "$BACKEND_DIR/app/routers/sync.py" \
  "$BACKEND_DIR/app/services/sync_service.py" \
  "$BACKEND_DIR/app/services/sync_modules/"*.py

echo "Kjører guardrail-tester..."
export PYTHONPATH="$BACKEND_DIR"
"$PY" -m unittest \
  tests.test_sync_jobs \
  tests.test_sync_job_acquire_guardrail \
  tests.test_paths_and_fit \
  tests.test_force_refresh_parquet \
  tests.test_summary_activity_type_filter \
  tests.test_sleep_and_hrv_sync.SleepAndHrvSyncTests.test_sleep_sync_retries_previously_missing_date_on_force_refresh \
  tests.test_sleep_and_hrv_sync.SleepAndHrvSyncTests.test_hrv_sync_retries_previously_missing_date_on_force_refresh \
  -v

echo "Starter API i testmodus (SKIP_GARMIN_INIT=true) for smoke..."
export SKIP_GARMIN_INIT=true
export DATABASE_URL=sqlite:///:memory:
export PYTHONPATH="$BACKEND_DIR"
"$PY" -m uvicorn app.main:app --app-dir "$BACKEND_DIR" --host "$HOST" --port "$PORT" >/tmp/preflight_uvicorn.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" >/dev/null 2>&1 || true' EXIT

echo "Venter på at API blir klart..."
READY_HTTP=""
for _ in $(seq 1 45); do
  READY_HTTP="$(curl -s -o /tmp/preflight_ready.json -w "%{http_code}" "$BASE_URL/" || true)"
  if [[ "$READY_HTTP" == "200" ]]; then
    break
  fi
  sleep 1
done

echo "Smoke: root og openapi..."
ROOT_HTTP="$(curl -s -o /tmp/preflight_root.json -w "%{http_code}" "$BASE_URL/")"
OPENAPI_HTTP="$(curl -s -o /tmp/preflight_openapi.json -w "%{http_code}" "$BASE_URL/openapi.json")"
if [[ "$ROOT_HTTP" != "200" || "$OPENAPI_HTTP" != "200" ]]; then
  echo "NO-GO: Root/OpenAPI feilet (root=$ROOT_HTTP, openapi=$OPENAPI_HTTP)"
  exit 1
fi

echo "Smoke: sync lock (fit download)..."
TMP_FIRST="/tmp/preflight_fit_first.json"
TMP_SECOND="/tmp/preflight_fit_second.json"
curl -s -X POST "$BASE_URL/api/sync/fit-data/download?limit=5" >"$TMP_FIRST" &
P1=$!
curl -s -X POST "$BASE_URL/api/sync/fit-data/download?limit=5" >"$TMP_SECOND" &
P2=$!
wait "$P1" "$P2"
FIRST_RESP="$(cat "$TMP_FIRST")"
SECOND_RESP="$(cat "$TMP_SECOND")"

JOB1="$("$PY" - <<'PY'
import json,sys
data=json.loads(sys.stdin.read() or "{}")
print(data.get("job_id",""))
PY
<<<"$FIRST_RESP")"
JOB2="$("$PY" - <<'PY'
import json,sys
data=json.loads(sys.stdin.read() or "{}")
print(data.get("job_id",""))
PY
<<<"$SECOND_RESP")"
REUSED2="$("$PY" - <<'PY'
import json,sys
data=json.loads(sys.stdin.read() or "{}")
print(str(data.get("reused_existing_job", False)).lower())
PY
<<<"$SECOND_RESP")"

if [[ -z "$JOB1" && -n "$JOB2" ]]; then
  JOB1="$JOB2"
fi
if [[ -z "$JOB2" && -n "$JOB1" ]]; then
  JOB2="$JOB1"
fi

# Robust vurdering:
# - PASS hvis andre kall rebruker eksisterende jobb.
# - Ellers: sjekk om første jobb allerede er ferdig. Da er ny jobb tillatt.
LOCK_OK="$("$PY" - "$FIRST_RESP" "$SECOND_RESP" <<'PY'
import json,sys

first = json.loads(sys.argv[1] or "{}")
second = json.loads(sys.argv[2] or "{}")
j1 = str(first.get("job_id", "")).strip()
j2 = str(second.get("job_id", "")).strip()

# Samme job_id betyr at duplicate-start ble hindret.
if j1 and j2 and j1 == j2:
    print("true")
    raise SystemExit(0)

# Alternativt: eksplisitt reused-flagg.
if bool(first.get("reused_existing_job")) or bool(second.get("reused_existing_job")):
    print("true")
    raise SystemExit(0)

print("false")
PY
)"

if [[ "$LOCK_OK" != "true" ]]; then
  STATUS1_JSON="$(curl -s "$BASE_URL/api/sync/status/$JOB1" || true)"
  STATUS1="$("$PY" - <<'PY'
import json,sys
try:
    data=json.loads(sys.stdin.read() or "{}")
except Exception:
    data={}
print(data.get("status",""))
PY
<<<"$STATUS1_JSON")"
  if [[ "$STATUS1" == "completed" || "$STATUS1" == "failed" ]]; then
    LOCK_OK="true"
    echo "Merk: første jobb var allerede ferdig ($STATUS1) før andre kall."
  fi
fi

if [[ "$LOCK_OK" != "true" ]]; then
  echo "NO-GO: Lock/duplicate prevention ser feil ut."
  echo "First:  $FIRST_RESP"
  echo "Second: $SECOND_RESP"
  exit 1
fi

echo "Smoke: status-endepunkt..."
STATUS_HTTP="$(curl -s -o /tmp/preflight_status.json -w "%{http_code}" "$BASE_URL/api/sync/status/$JOB1")"
if [[ "$STATUS_HTTP" == "404" && -n "$JOB2" && "$JOB2" != "$JOB1" ]]; then
  STATUS_HTTP="$(curl -s -o /tmp/preflight_status.json -w "%{http_code}" "$BASE_URL/api/sync/status/$JOB2")"
fi
if [[ "$STATUS_HTTP" != "200" ]]; then
  echo "Advarsel: status-endepunkt ga http=$STATUS_HTTP i denne kjøringen."
  echo "Fortsetter siden lock-testen allerede er verifisert."
fi

echo
echo "GO: Preflight bestått."
echo "- root/openapi: OK"
echo "- tester: OK"
echo "- sync lock: OK"
if [[ "$STATUS_HTTP" == "200" ]]; then
  echo "- status-endepunkt: OK"
else
  echo "- status-endepunkt: WARN (http=$STATUS_HTTP)"
fi
