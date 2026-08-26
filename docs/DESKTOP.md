# Treningsanalyse — Windows desktop

Electron shell around the existing FastAPI + Next.js stack. SQLite remains the desktop database.

## Architecture

```text
Treningsanalyse.exe (Electron)
  ├── treningsanalyse-backend.exe   # FastAPI on 127.0.0.1:<dynamic>
  ├── Next.js standalone server.js  # 127.0.0.1:<dynamic>
  └── BrowserWindow → frontend
```

Mutable data lives under Electron `app.getPath('userData')` (typically `%LOCALAPPDATA%\Treningsanalyse\`).

## Developer commands (repo root)

```bash
# Prepare Next standalone (+ optional Linux PyInstaller smoke)
npm run desktop:prepare

# Electron against local .venv backend + next start (after frontend build)
npm run desktop:dev

# Full Windows installer (run on Windows or via GitHub Actions)
npm run desktop:dist
```

GitHub Actions: `.github/workflows/desktop-windows.yml` (workflow_dispatch + path filters) uploads the NSIS installer artifact.

App icon: `desktop/assets/icon.svg` (source), `icon.png` / `icon.ico` for Electron/NSIS. PWA icons live in `frontend/public/icons/`. Regenerate `.ico` after PNG changes with `npm run icons --prefix desktop`.

Production Next.js uses **Electron-as-Node** (`ELECTRON_RUN_AS_NODE=1` + `process.execPath`) so end users do not need a separate Node install. Windows CI may still bundle `node.exe` as an optional override.

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
