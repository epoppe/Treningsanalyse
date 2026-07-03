# AGENTS.md

## Cursor Cloud specific instructions

Treningsanalyse is a Garmin training-analysis app: a FastAPI backend (`backend/`) and a Next.js 14 frontend (`frontend/`). The update script provisions both, so the notes below focus on running/testing, not installation.

### Services and how to run them (from repo root)
- Backend (FastAPI, port 8000): `npm run dev:backend`. This wraps `backend/.venv/bin/python -m uvicorn app.main:app --reload` with `SKIP_GARMIN_INIT=true`, which lets the API boot **without** Garmin credentials. Standard run commands live in root `package.json`.
- Frontend (Next.js, port 3000): `npm run dev`. The frontend proxies `/api/*` to `http://localhost:8000` via `frontend/next.config.js` rewrites, so the backend must be running for data to load.
- Both are dev servers with hot reload; run each in its own long-lived (tmux) session.

### Tests / lint / build
- Backend tests: `npm test` (Python `unittest`). Note: ~6 advanced performance-metric tests (`test_performance_metrics`, parts of `test_analysis_atomicity`/`test_sync_metrics`/`test_coaching_analysis`) fail on a clean checkout independent of dependency versions — these are pre-existing app-logic failures, not an environment problem.
- Backend guardrails (the subset the project treats as critical): `npm run test:guardrails`, or the fuller smoke `npm run preflight` (`backend/scripts/preflight.sh`).
- Frontend lint: `npm run lint`. Frontend build: `npm run build`.

### Non-obvious gotchas
- `requirements.txt` historically omitted `polars`, `pyarrow`, and `plotly`, but all three are imported at startup (`app/storage.py`, `app/routers/activities.py`) — the backend will not import without them. They are now listed in `backend/requirements.txt`.
- The SQLite DB lives at `backend/data/treningsanalyse.db` (gitignored) and is auto-created + migrated on backend startup. On a fresh VM it is **empty** (no activities) because there is no Garmin data; the app pages render but lists are empty until data is synced or seeded.
- Real Garmin sync needs `GARMIN_EMAIL` / `GARMIN_PASSWORD` in `backend/.env` (copied from `backend/env.example`). Without them, keep `SKIP_GARMIN_INIT=true`.
- Garmin auth uses **python-garminconnect** (not garth): `app/services/garmin_auth.py` (`GarminAuthManager`) owns login, token-cache (`<TOKEN_DIR>/garmin_tokens.json`), auto-refresh, and typed failures (`GarminReauthRequiredError`/`GarminMFARequiredError`/`GarminRateLimitError`). A legacy garth `oauth2_token.json` in `TOKEN_DIR` is read once and migrated into the native cache; garth is never used for login/renewal. `garth` stays in `requirements.txt` only for old top-level scripts.
- `main.py` honors `SKIP_GARMIN_INIT`; without it, startup runs garminconnect's login strategies (with intentional anti-WAF sleeps up to ~20s) and can be slow — always keep `SKIP_GARMIN_INIT=true` in dev.
- Re-auth (401/MFA/changed login) sends a Telegram alert if `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are set (see `app/services/telegram_notifier.py`); unset = no-op.
- Activity detail pages (`/activities/{id}`) require a **numeric** `activity_id` (route is typed `int`); the statistics page needs monthly-summary data to leave its loading state. Both are data dependencies, not bugs.
- Redis is optional: without it the backend logs a warning and uses an in-memory cache.
- `python3 -m venv` requires the system `python3-venv` package (already present in the VM snapshot).
