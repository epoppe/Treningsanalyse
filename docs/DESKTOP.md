# Treningsanalyse — Windows desktop

Electron shell around the existing FastAPI + Next.js stack. SQLite remains the desktop database.

## Architecture

```text
Treningsanalyse.exe (Electron)
  ├── resources/backend/treningsanalyse-backend/
  │     treningsanalyse-backend.exe   # PyInstaller COLLECT (FastAPI @ 127.0.0.1)
  ├── resources/frontend/
  │     server.js + node.exe          # Next.js standalone
  └── BrowserWindow → frontend
```

Mutable data lives under Electron `app.getPath('userData')` (typically `%LOCALAPPDATA%\Treningsanalyse\` or `%APPDATA%\treningsanalyse-desktop\`):

```text
<userData>/
  data/treningsanalyse.db
  tokens/
  fit/
  cache/
  logs/
  backups/
  exports/
```

`Program Files\Treningsanalyse\resources\` is **read-only**. `app.config` does not mkdir at import time; directories are created only after Settings resolves `TRAININGSANALYSE_DATA_DIR`.

## Developer commands (repo root)

```bash
# Prepare Next standalone (+ optional Linux PyInstaller smoke)
npm run desktop:prepare

# Electron against local .venv backend + next start (after frontend build)
npm run desktop:dev

# Full Windows installer (run on Windows or via GitHub Actions)
npm run desktop:dist
```

GitHub Actions: `.github/workflows/desktop-windows.yml` builds unpacked app, runs `scripts/desktop-packaged-smoke.sh` (layout + `/health/live`), then NSIS + artifact upload.

App icon: `desktop/assets/icon.svg` (source), `icon.png` / `icon.ico` for Electron/NSIS. PWA icons live in `frontend/public/icons/`. Regenerate `.ico` after PNG changes with `npm run icons --prefix desktop`.

Production Next.js prefers bundled `node.exe` under `resources/frontend/`; falls back to Electron-as-Node (`ELECTRON_RUN_AS_NODE=1`).

## Garmin Connect (synkronisering)

Synk mot Garmin krever enten:

1. **Credentials** i `%LOCALAPPDATA%\Treningsanalyse\config\.env` (opprettes automatisk første gang):
   ```env
   GARMIN_EMAIL=din@epost.example
   GARMIN_PASSWORD=ditt_passord
   ```
   Åpnes via **Fil → Garmin-innstillinger…** i desktop-appen.

2. **Eller** kopier `tokens/garmin_tokens.json` (eller legacy `oauth2_token.json`) fra tidligere installasjon til AppData `tokens/`.

Uten dette returnerer «Synk nye» en tydelig feilmelding (HTTP 422), ikke en generisk 500.

## Import existing database

**In the app:** Fil → Importer eksisterende database…

**CLI:**

```bash
cd backend
TRAININGSANALYSE_DATA_DIR="C:/Users/You/AppData/Local/Treningsanalyse" \
  .venv/bin/python scripts/import_database.py /path/to/treningsanalyse.db --overwrite
```

Never modifies the source file. Overwrite takes a backup under `backups/`.

## MCP against desktop data

```bash
export DATABASE_URL="sqlite:///C:/Users/You/AppData/Local/Treningsanalyse/data/treningsanalyse.db"
export DATA_DIR="C:/Users/You/AppData/Local/Treningsanalyse/data"
export TOKEN_DIR="C:/Users/You/AppData/Local/Treningsanalyse/tokens"
cd backend && python mcp_server.py
```

## Security notes

- Backend binds **127.0.0.1 only**
- Single-instance lock (one SQLite writer)
- No credentials in the installer; Garmin tokens stay in AppData `tokens/`
