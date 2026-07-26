# Continuous Integration

GitHub Actions-pipeline: `.github/workflows/ci.yml`

Kjører på push/PR mot `main`. Feiler ved lint-, test-, type- eller build-feil.

## Backend-jobb

| Steg | Verktøy | Merknad |
|------|---------|---------|
| Lint | Ruff | Kritiske regler (`E9`, `F63`, `F7`, `F82`) — se `backend/ruff.toml` |
| Types | MyPy | Gradvis scope: `app/database` + `app/config.py` — se `backend/mypy.ini` |
| Migrasjon | Alembic + pytest | `alembic upgrade head` + `tests/test_alembic_migrations.py` |
| Tester | pytest | Stabil CI-suite (ikke full unittest med kjente app-logic-feil) |
| Smoke | `scripts/ci_smoke_api.sh` | `/`, `/openapi.json`, `/health` med schema-versjon |

## Frontend-jobb

| Steg | Kommando |
|------|----------|
| Install | `npm ci` |
| Lint | `npm run lint` (ESLint / next lint) |
| Types | `npx tsc --noEmit` |
| Build | `npm run build` |

## Lokalt

```bash
# Backend
cd backend
pip install -r requirements-dev.txt
ruff check app/
mypy
pytest tests/test_alembic_migrations.py -v
bash scripts/ci_smoke_api.sh

# Frontend
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm run build

# Fra repo-rot
npm run ci:backend
npm run ci:frontend
```

## Utvidelser (senere)

- Utvid Ruff `select` etter hvert som whitespace/import-støy ryddes
- Utvid MyPy `files` til routers/services
- Ta inn flere pytest-moduler når guardrail-tester er tracket i git
