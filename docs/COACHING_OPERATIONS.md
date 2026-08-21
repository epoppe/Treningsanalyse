# Coaching Operations Runbook

Copy-pasteable commands for Treningsanalyse coaching ops. From repo root unless noted.

Set `SKIP_GARMIN_INIT=true` for local API work without Garmin credentials.

## Health

```bash
bash backend/scripts/coaching_ops.sh health
# or
cd backend && SKIP_GARMIN_INIT=true PYTHONPATH=. .venv/bin/python -c "
from app.database.session import SessionLocal
from app.services.coaching_health_service import CoachingHealthService
print(CoachingHealthService(SessionLocal()).report())
"
```

Inspect: `status`, `checks.db_migration`, `checks.data_freshness`, `issues`.

## Integrity

```bash
bash backend/scripts/coaching_ops.sh integrity
```

Findings include `code`, `severity`, `count`, `repairable`. Never auto-repairs destructively.

## Prospective evidence report

```bash
bash backend/scripts/coaching_ops.sh prospective
```

Recorded recommendations only. Every section has `sample_count`. Do not overclaim.

## Monthly coaching review

```bash
bash backend/scripts/coaching_ops.sh monthly
```

Answers the 10 operational questions. Sparse data → "what should NOT change".

## Export coaching data (no secrets)

```bash
bash backend/scripts/coaching_ops.sh export /tmp/coaching_export.json
```

Manifest never includes Garmin tokens/credentials (`contains_credentials: false`).

## Restore drill

```bash
cd backend
PYTHONPATH=. .venv/bin/python - <<'PY'
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database.migrations import run_migrations
from app.services.coaching_data_export_service import CoachingDataExportService
import json

payload = json.load(open("/tmp/coaching_export.json"))
assert not payload.get("contains_credentials")
url = "sqlite:////tmp/coaching_restore.db"
engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
run_migrations(engine, url)
db = sessionmaker(bind=engine)()
report = CoachingDataExportService(db).restore(payload)
print(report)
PY
```

## Alembic validation

```bash
bash backend/scripts/coaching_ops.sh alembic-check
npm run db:current
npm run db:upgrade
```

CI also runs: empty DB → upgrade head → pytest alembic → API smoke with `schema_at_head`.

Do **not** auto-generate migrations in CI.

## Active / shadow model

```bash
bash backend/scripts/coaching_ops.sh active-model
```

Shadow recommendations are stored separately and must never mutate the active plan. Promotion requires `ValidationRun` via `CoachingModelRegistry.promote(...)`.

## Stale data diagnosis

1. `coaching_ops.sh health` → `data_freshness` (missing vs stale).
2. Check `last_successful_garmin_sync`.
3. Latency: use `DataLatencyMonitor` (pipeline lag even when source exists).
4. Data-quality trend: `DataQualityTrendService` — separates input degradation from model issues.

## Failed sync recovery

1. Confirm `SKIP_GARMIN_INIT` unset only when credentials exist in `backend/.env`.
2. Inspect sync lock / jobs (see `docs/DATABASE_MIGRATIONS.md` and sync docs).
3. Re-run sync with known-good credentials; do not delete recommendation history.
4. Re-check health + integrity after sync.

## CI quality gate

```bash
npm run ci:backend
```

Must include coaching invariant suite. Failures block merge to `main`.
