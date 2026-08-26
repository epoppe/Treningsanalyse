# AGENTS.md

## Cursor Cloud specific instructions

Treningsanalyse is a Garmin training-analysis app: a FastAPI backend (`backend/`) and a Next.js 14 frontend (`frontend/`). The update script provisions both, so the notes below focus on running/testing, not installation.

### Services and how to run them (from repo root)
- Backend (FastAPI, port 8000): `npm run dev:backend`. This wraps `backend/.venv/bin/python -m uvicorn app.main:app --reload` with `SKIP_GARMIN_INIT=true`, which lets the API boot **without** Garmin credentials. Standard run commands live in root `package.json`.
- Frontend (Next.js, port 3000): `npm run dev`. The frontend proxies `/api/*` and `/health*` to `http://localhost:8000` via `frontend/next.config.js` rewrites, so the backend must be running for data to load.
- Both are dev servers with hot reload; run each in its own long-lived (tmux) session.
- Prod-like local: `npm run start:local` (`scripts/start-local.sh`) or `docker compose up --build`. See `docs/DEPLOYMENT.md`.
- Desktop smoke (Linux): `npm run desktop:smoke` after `npm run desktop:prepare`. See `docs/DESKTOP.md`.
- Health probes: `/health/live` (liveness), `/health/ready` (200 ready / 503 not ready).

### Tests / lint / build
- Backend tests: `npm test` (Python `unittest`).
- Backend guardrails (critical sync/schema/security subset): `npm run test:guardrails`, or fuller smoke `npm run preflight` (`backend/scripts/preflight.sh`). These point at tracked tests on `main` (sync lock, no `asyncio.run`, batch/checkpoint, alembic, runtime hardening, layers, security, settings, metric graph).
- CI suite (GitHub Actions): `npm run ci:backend` / `npm run ci:frontend` — se `docs/CI.md` og `.github/workflows/ci.yml`.
- Frontend lint: `npm run lint`. Frontend build: `npm run build`.
- VO2 coverage helper: `npm run diagnose:vo2max` (optional local diagnose after Garmin performance sync).

### Non-obvious gotchas
- `requirements.txt` historically omitted `polars`, `pyarrow`, and `plotly`, but all three are imported at startup (`app/storage.py`, `app/routers/activities.py`) — the backend will not import without them. They are now listed in `backend/requirements.txt`.
- The SQLite DB lives at `backend/data/treningsanalyse.db` (gitignored) and is auto-created + migrated on backend startup. On a fresh VM it is **empty** (no activities) because there is no Garmin data; the app pages render but lists are empty until data is synced or seeded.
- Real Garmin sync needs `GARMIN_EMAIL` / `GARMIN_PASSWORD` in `backend/.env` (copied from `backend/env.example`). Without them, keep `SKIP_GARMIN_INIT=true`.
- Garmin auth uses **python-garminconnect** (not garth): `app/services/garmin_auth.py` (`GarminAuthManager`) owns login, token-cache (`<TOKEN_DIR>/garmin_tokens.json`), auto-refresh, and typed failures (`GarminReauthRequiredError`/`GarminMFARequiredError`/`GarminRateLimitError`). A legacy garth `oauth2_token.json` in `TOKEN_DIR` is read once and migrated into the native cache; garth is never used for login/renewal. `garth` stays in `requirements.txt` only for old top-level scripts.
- `main.py` honors `SKIP_GARMIN_INIT`; without it, startup runs garminconnect's login strategies (with intentional anti-WAF sleeps up to ~20s) and can be slow — always keep `SKIP_GARMIN_INIT=true` in dev.
- Re-auth (401/MFA/changed login) sends a Telegram alert if `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are set (see `app/services/telegram_notifier.py`); unset = no-op.
- Activity detail pages (`/activities/{id}`) require a **numeric** `activity_id` (route is typed `int`); the statistics page needs monthly-summary data to leave its loading state. Both are data dependencies, not bugs.
- Redis is optional (default `REDIS_ENABLED=false`): without it the backend uses an in-memory cache. Set `REDIS_ENABLED=true` to use Redis.
- `python3 -m venv` requires the system `python3-venv` package (already present in the VM snapshot).
- `/api/debug/db-info` requires `DEBUG=true`. Do not expose the API publicly without an ACL (`docs/DEPLOYMENT.md`, `docs/SECURITY.md`).
- Windows desktop packaging: see `docs/DESKTOP.md`. Data root override: `TRAININGSANALYSE_DATA_DIR`. Database portability notes: `docs/DATABASE_PORTABILITY.md`.
