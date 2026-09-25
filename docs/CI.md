# Continuous Integration

GitHub Actions-pipeline: `.github/workflows/ci.yml`

Kjører på push mot `main` og på pull requests mot alle brancher, inkludert stablede PR-er. Feiler ved lint-, test-, type- eller build-feil.

Backend-jobben kaller `backend/scripts/ci_backend.sh`. Samme script er `npm run ci:backend`. Det finnes ikke en egen testliste i workflow-filen.

## Backend-jobb

| Steg | Verktøy | Merknad |
|------|---------|---------|
| Lint | Ruff | `E9`, `F63`, `F7`, `F82`, `F811` — se `backend/ruff.toml` |
| Types | MyPy | `app/database`, `app/config.py`, `outcome_maturity`, `sample_sufficiency_policy` — se `backend/mypy.ini` |
| Migrasjon | Alembic | Single-head assert + `alembic upgrade head` mot `/tmp/ci-migrate.db` |
| Tester | pytest | Hele `backend/tests` |
| Smoke | `scripts/ci_smoke_api.sh` | `/`, `/openapi.json`, `/health` med schema-versjon |
| Import | `from app.main import app` | Startup/import smoke |

`npm run test:coaching` kjører samme pytest-tre (`ci_backend.sh --pytest-only`), uten ruff, mypy, migrasjon og smoke.

### Full suite, 25. september 2026

`pytest tests` var 475 grønne og 1 rød før denne runden. Den røde var `test_debug_db_info_available_when_debug`: testen patchet `app.config.settings` etter at lazy-singletonen var byttet, mens ruten leser instansen `app.main` bandt ved import. Det er testisolasjon, ikke en produksjonsfeil i debug-porten. Testen patcher nå `app.main.settings`.

Ytelsestester for performance metrics var grønne i samme kjøring. Den gamle CI-kommentaren om at kjente app-logikkfeil holdes utenfor stemte ikke lenger med suite-resultatet.

### Coaching suites som fortsatt må være grønne

De ligger i `tests/` og kjøres fordi CI tar hele treet:

- `test_coaching_hardening.py` — rollback, idempotency, unavailable/pain, shadow, export
- `test_coaching_v8.py` — explanation, consistency, safety golden
- `test_coaching_correctness.py` — drift semantics, freshness, integrity
- `test_coaching_v9_operational.py` — sufficiency, restore, prospective, monitors, alembic step-upgrade
- `test_prospective_evidence_correctness.py` — HRV sign, canonical observations, maturity, calibration, model-change evidence
- `test_coaching_evidence_feedback_api.py` — read-only coaching evidence dashboard and idempotent activity feedback
- `test_canonical_observation_scale.py` — supersede-lukking og query-count, ikke millisekunder
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
| Tester | `npm test -- --watchAll=false` |
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

- Ruff `F401` er fortsatt av: omtrent 125 ubrukte importer. Ikke slå det på i en formatterings-PR.
- MyPy på coaching-ORM-modulene stopper på `Column[...]`-støy fra eldre `Column()`-modeller. Rene moduler er inne. Ikke slå på strict globalt.
- Query-count-guardrailen for canonical observation ligger i `test_canonical_observation_scale.py`.
