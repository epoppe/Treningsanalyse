# Local / self-host deployment

Treningsanalyse is designed for a personal LAN/home server. The API has **no user authentication** — do not expose it on the public internet without a reverse proxy ACL.

## Quick paths

| Mode | Command | Notes |
|------|---------|--------|
| Dev (hot reload) | `npm run dev:backend` + `npm run dev` | `SKIP_GARMIN_INIT=true` on backend |
| Prod-like local | `./scripts/start-local.sh --build` | uvicorn (no reload) + `next start` |
| Docker | `docker compose up --build` | Optional Redis: `docker compose --profile redis up --build` |

## Environment

1. Copy `backend/env.example` → `backend/.env`
2. Copy `frontend/.env.example` → `frontend/.env.local` (optional)
3. Recommended local defaults:
   - `SKIP_GARMIN_INIT=true` until you sync
   - `REDIS_ENABLED=false` (in-memory cache)
   - `DEBUG=false`
   - `CORS_ORIGINS` includes your UI origin (and LAN IP if using PWA from a phone)

## Health probes

| Path | Meaning | HTTP |
|------|---------|------|
| `/health/live` | Process up | 200 |
| `/health/ready` | DB + schema + data dir | 200 ready / **503** not ready |
| `/health` | Schema version summary | 200 |

`/api/debug/db-info` is gated behind `DEBUG=true`.

## SQLite data & backup

- Default DB: `backend/data/treningsanalyse.db` (Docker volume `backend_data`)
- Tokens: `backend/tokens/` (Docker volume `backend_tokens`) — never commit
- Portable zip (no tokens): `backend/.venv/bin/python backend/scripts/portable_data_bundle.py`
- Prefer stopping writers (or use `sqlite3 … .backup`) before copying a live DB

## LAN / PWA

1. Bind carefully — prefer localhost for daily use
2. If the phone installs the PWA against `http://<lan-ip>:3000`, add that origin to `CORS_ORIGINS` and set `NEXT_PUBLIC_API_URL` to the reachable API URL
3. Offline shell shows «Treningsanalyse-serveren er ikke tilgjengelig.» — start backend again; no offline data sync yet

## Security checklist

- [ ] Not publicly reachable without ACL
- [ ] `DEBUG=false` in daily use
- [ ] `ALLOWED_HOSTS` set if you terminate TLS / use a hostname
- [ ] Garmin + Telegram secrets only in `.env` / compose secrets
