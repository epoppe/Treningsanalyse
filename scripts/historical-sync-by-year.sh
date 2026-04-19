#!/usr/bin/env bash
# Historisk aktivitetssynk år for år mot /api/sync/activities/historical
# Krever kjørende backend (standard http://127.0.0.1:8000).
#
# Bruk:
#   ./scripts/historical-sync-by-year.sh
#   FIRST_YEAR=2018 LAST_YEAR=2022 BASE_URL=http://127.0.0.1:8000 ./scripts/historical-sync-by-year.sh
#
# Miljøvariabler:
#   BASE_URL              API-rot (default: http://127.0.0.1:8000)
#   FIRST_YEAR            Laveste år i intervallet (default: 2018)
#   LAST_YEAR             Høyeste år i intervallet (default: 2022)
#   POLL_SEC              Sekunder mellom status-sjekk (default: 15)
#   PAUSE_BETWEEN_YEARS   Pause etter fullført år før neste POST (default: 10)
#   MAX_WAIT_SEC          Maks ventetid per år (default: 172800 = 48t)

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
FIRST_YEAR="${FIRST_YEAR:-2018}"
LAST_YEAR="${LAST_YEAR:-2022}"
POLL_SEC="${POLL_SEC:-15}"
PAUSE_BETWEEN_YEARS="${PAUSE_BETWEEN_YEARS:-10}"
MAX_WAIT_SEC="${MAX_WAIT_SEC:-172800}"

PY="${PY:-python3}"

count_activities() {
  curl -s "${BASE_URL}/api/activities/count" | "$PY" -c "import sys,json; print(json.load(sys.stdin).get('count','?'))"
}

get_json_field() {
  # stdin: JSON, arg1: key
  "$PY" -c "import sys,json; d=json.load(sys.stdin); print(d.get('$1',''))"
}

start_historical_year() {
  local year="$1"
  local url="${BASE_URL}/api/sync/activities/historical?start_date=${year}-01-01&end_date=${year}-12-31"
  curl -s -X POST "$url"
}

poll_job() {
  local job_id="$1"
  local elapsed=0
  while (( elapsed < MAX_WAIT_SEC )); do
    local body
    body=$(curl -s "${BASE_URL}/api/sync/status/${job_id}")
    local status
    status=$(echo "$body" | get_json_field status)
    local msg
    msg=$(echo "$body" | "$PY" -c "import sys,json; d=json.load(sys.stdin); print(d.get('message','')[:120])" 2>/dev/null || echo "")
    echo "    status=${status} ${msg}"
    if [[ "$status" == "completed" ]]; then
      return 0
    fi
    if [[ "$status" == "failed" ]]; then
      echo "$body" | "$PY" -m json.tool 2>/dev/null || echo "$body"
      return 1
    fi
    sleep "$POLL_SEC"
    elapsed=$((elapsed + POLL_SEC))
  done
  echo "Timeout etter ${MAX_WAIT_SEC}s for job ${job_id}" >&2
  return 1
}

if (( FIRST_YEAR > LAST_YEAR )); then
  echo "FIRST_YEAR må være <= LAST_YEAR (f.eks. FIRST_YEAR=2018 LAST_YEAR=2022)" >&2
  exit 1
fi

echo "Backend: ${BASE_URL}"
echo "År: ${LAST_YEAR} ned til ${FIRST_YEAR} (synkroniserer eldre data i kontrollerte bolker)"
echo "Start aktivitetstall: $(count_activities)"
echo ""

for (( year=LAST_YEAR; year>=FIRST_YEAR; year-- )); do
  echo "=== År ${year} ==="
  resp=$(start_historical_year "$year")
  job_id=$(echo "$resp" | get_json_field job_id)
  reused=$(echo "$resp" | get_json_field reused_existing_job)

  if [[ -z "$job_id" ]]; then
    echo "Kunne ikke lese job_id fra svar:" >&2
    echo "$resp" | "$PY" -m json.tool 2>/dev/null || echo "$resp" >&2
    exit 1
  fi

  echo "job_id=${job_id} reused_existing_job=${reused:-false}"
  if ! poll_job "$job_id"; then
    echo "Stoppet pga feil/timeout for år ${year}." >&2
    exit 1
  fi
  echo "Aktivitetstall etter ${year}: $(count_activities)"
  if (( year > FIRST_YEAR )); then
    echo "Pause ${PAUSE_BETWEEN_YEARS}s før neste år..."
    sleep "$PAUSE_BETWEEN_YEARS"
  fi
  echo ""
done

echo "Ferdig. Slutt aktivitetstall: $(count_activities)"
