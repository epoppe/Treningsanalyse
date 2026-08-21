# Continuous Integration

GitHub Actions-pipeline: `.github/workflows/ci.yml`

Kjører på push/PR mot `main`. Feiler ved lint-, test-, type- eller build-feil.

## Backend-jobb

| Steg | Verktøy | Merknad |
|------|---------|---------|
| Lint | Ruff | Kritiske regler (`E9`, `F63`, `F7`, `F82`) — se `backend/ruff.toml` |
| Types | MyPy | Gradvis scope: `app/database` + `app/config.py` — se `backend/mypy.ini` |
| Migrasjon | Alembic + pytest | Single-head assert + `alembic upgrade head` + `tests/test_alembic_migrations.py` |
| Tester | pytest | Platform + **coaching invariant/operational suites** |
| Smoke | `scripts/ci_smoke_api.sh` | `/`, `/openapi.json`, `/health` med schema-versjon |
| Import | `from app.main import app` | Startup/import smoke |

### Coaching suites in CI (must stay green)

- `test_coaching_hardening.py` — rollback, idempotency, unavailable/pain, shadow, export
- `test_coaching_v8.py` — explanation, consistency, safety golden
- `test_coaching_correctness.py` — drift semantics, freshness, integrity
- `test_coaching_v9_operational.py` — sufficiency, restore, prospective, monitors, alembic step-upgrade
- `test_adaptive_coaching_v5.py` — preview no-persist, no-lookahead
- `test_adaptive_coaching_v7.py` — shadow isolation, promotion gate
- `test_analysis_workspace_api.py` — `/api/analysis/development|timeseries|relationships` wrappers

Required coaching invariants (fail CI on break):

- future data cannot alter historical recommendation
- shadow model cannot alter production plan
- unavailable day cannot receive workout
- safety guardrail cannot be overridden by personalization
- duplicate sync cannot duplicate execution
- recommendation supersede graph remains valid
- insufficient evidence cannot be reported as stable
- preview cannot persist state

## Frontend-jobb

| Steg | Kommando |
|------|----------|
| Install | `npm ci` |
| Lint | `npm run lint` (ESLint / next lint) |
| Types | `npx tsc --noEmit` |
| Build | `npm run build` |

## Lokalt

```bash
# Backend CI mirror
npm run ci:backend

# Coaching only
npm run test:coaching

# Ops helpers
npm run coaching:ops -- health

# Frontend
npm run ci:frontend
```

## Utvidelser (senere)

- Utvid Ruff `select` etter hvert som whitespace/import-støy ryddes
- Utvid MyPy `files` til routers/services
- Generous perf regression thresholds (catch 5×/10× / N+1 only)
