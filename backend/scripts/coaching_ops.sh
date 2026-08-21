#!/usr/bin/env bash
# Coaching operational helpers — copy-pasteable from docs/COACHING_OPERATIONS.md
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PY="${BACKEND_DIR}/.venv/bin/python"
[[ -x "$PY" ]] || PY="${PYTHON:-python3}"
cd "$BACKEND_DIR"
export PYTHONPATH="$BACKEND_DIR"
export SKIP_GARMIN_INIT="${SKIP_GARMIN_INIT:-true}"

cmd="${1:-help}"
shift || true

case "$cmd" in
  health)
    "$PY" - <<'PY'
from app.database.session import SessionLocal
from app.services.coaching_health_service import CoachingHealthService
db = SessionLocal()
try:
    import json
    print(json.dumps(CoachingHealthService(db).report(), indent=2, default=str))
finally:
    db.close()
PY
    ;;
  integrity)
    "$PY" - <<'PY'
from app.database.session import SessionLocal
from app.services.coaching_integrity_service import CoachingIntegrityService
import json
db = SessionLocal()
try:
    print(json.dumps(CoachingIntegrityService(db).check(), indent=2, default=str))
finally:
    db.close()
PY
    ;;
  prospective)
    "$PY" - <<'PY'
from app.database.session import SessionLocal
from app.services.prospective_evidence_report_service import ProspectiveEvidenceReportService
import json
db = SessionLocal()
try:
    print(json.dumps(ProspectiveEvidenceReportService(db).report(), indent=2, default=str))
finally:
    db.close()
PY
    ;;
  monthly)
    "$PY" - <<'PY'
from app.database.session import SessionLocal
from app.services.monthly_coaching_review_service import generate_monthly_coaching_review
import json
db = SessionLocal()
try:
    print(json.dumps(generate_monthly_coaching_review(db), indent=2, default=str))
finally:
    db.close()
PY
    ;;
  export)
    out="${1:-/tmp/coaching_export.json}"
    "$PY" - "$out" <<'PY'
import json, sys
from app.database.session import SessionLocal
from app.services.coaching_data_export_service import CoachingDataExportService
path = sys.argv[1]
db = SessionLocal()
try:
    payload = CoachingDataExportService(db).export_manifest()
    assert not payload.get("contains_credentials")
    open(path, "w").write(json.dumps(payload, indent=2, default=str))
    print(f"Wrote {path}")
finally:
    db.close()
PY
    ;;
  alembic-check)
    "$PY" - <<'PY'
from app.database.migrations import assert_single_alembic_head, get_schema_version
from app.database.session import engine
print("head", assert_single_alembic_head())
print(get_schema_version(engine))
PY
    ;;
  active-model)
    "$PY" - <<'PY'
from app.database.session import SessionLocal
from app.services.coaching_model_registry import CoachingModelRegistry
import json
db = SessionLocal()
try:
    print(json.dumps(CoachingModelRegistry(db).get_active("ranker"), indent=2, default=str))
finally:
    db.close()
PY
    ;;
  help|*)
    echo "Usage: $0 {health|integrity|prospective|monthly|export [path]|alembic-check|active-model}"
    exit 1
    ;;
esac
