# Treningsanalyse 🏃‍♂️

En kraftig web-applikasjon for analyse av treningsdata fra Garmin.

## ✨ Funksjoner

- 📊 Detaljert analyse av treningsaktiviteter
- ⚡ Automatisk synkronisering fra Garmin Connect
- 📈 Avanserte metrics: TSS, Power, Løpsøkonomi, Negative Split, Decoupling
- 💓 HRV og Body Battery tracking
- 📉 Training Stress og Recovery analyse
- 🎯 Ukentlige og månedlige sammendrag

## 🚀 Kom i gang

**Se `START_HERE.md` for detaljert oppstartsinstruks!**

### Rask start

```bash
# 1. Konfigurer miljøvariabler
cd backend
copy env.example .env
# Rediger .env med dine Garmin credentials

# 2. Start backend
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Start frontend (ny terminal)
cd frontend
npm install
npm run dev
```

Åpne http://localhost:3000

## 🪟 Windows-skrivebord (installer)

Se **`docs/DESKTOP.md`**. Kort:

```bash
npm run desktop:prepare   # Next standalone (+ docs for PyInstaller)
npm run desktop:dist      # NSIS installer (kjør på Windows / GitHub Actions)
```

Database: SQLite under `%LOCALAPPDATA%\Treningsanalyse\data\`. Portabilitet: `docs/DATABASE_PORTABILITY.md`.

## 🤖 Automatisk Beregningssystem

**NYT!** Alle beregnede verdier beregnes automatisk ved synkronisering:

- ✅ TSS (Training Stress Score)
- ✅ Power (estimert løpeffekt)
- ✅ Løpsøkonomi (hastighet/puls-forhold)
- ✅ Negative Split
- ✅ Decoupling (aerob dekobling)

Verdiene lagres i databasen og er umiddelbart tilgjengelige uten re-beregning!

**Les mer:** `AUTO_CALCULATION_SYSTEM.md`

## 🏗️ Teknologi

- **Frontend:** Next.js 14, React, Redux, Styled-components
- **Backend:** Python, FastAPI, SQLAlchemy, Alembic
- **Database:** SQLite (optimalisert med WAL-mode)
- **Data:** Garmin Connect API, FIT-fil parsing

## 🗄️ Database-migrasjoner

Schema administreres med Alembic (ikke lenger `create_all` + manuelle `migrate_*.py` ved oppstart).

```bash
npm run db:upgrade    # alembic upgrade head
npm run db:current    # vis schema-revisjon
```

Health check med schema-versjon: `GET /health`

Se `docs/DATABASE_MIGRATIONS.md` for detaljer.

## 🔁 CI

GitHub Actions (`.github/workflows/ci.yml`) kjører på PR/push til `main`:

- **Backend:** Ruff, MyPy, Alembic-migrasjonstest, pytest, API-smoke
- **Frontend:** `npm ci`, ESLint, TypeScript, `next build`

Lokalt: `npm run ci:backend` / `npm run ci:frontend`. Se `docs/CI.md`.

## 📚 Dokumentasjon

- **START_HERE.md** - Start her! Komplett guide og trygg oppstart
- **REPO_NOTES.md** - Struktur og lavrisiko vedlikeholdsnotater
- **docs/DATABASE_MIGRATIONS.md** - Alembic-migrasjoner
- **docs/CI.md** - GitHub Actions CI
- **DEVELOPMENT_NOTES.md** - Utviklernotater om frontend-/Node-struktur
- **AUTO_CALCULATION_SYSTEM.md** - Automatisk beregningssystem
- **IMPLEMENTATION_SUMMARY.md** - Oversikt over optimaliseringer
- **OPTIMIZATION_CHANGES.md** - Detaljerte endringer
- **CACHE_SYSTEM.md** - Cache-arkitektur
- **ANALYTICS_METRICS.md** - EF og aerobic decoupling formler

## 🔧 API Endepunkter

### System
- `GET /health` - Health check med Alembic schema-versjon

### Synkronisering
- `POST /api/sync/full-sync` - Full synkronisering (aktiviteter + helsedata)
- `POST /api/sync/sync-new-activities` - Synkroniser nye aktiviteter

### Aktiviteter
- `GET /api/activities` - Hent aktiviteter
- `GET /api/activities/{id}` - Hent spesifikk aktivitet
- `GET /api/activities/{id}/details` - Hent FIT-data for aktivitet

### Cache/Beregninger
- `POST /api/cache/calculate-all` - Beregn manglende verdier
- `GET /api/cache/stats` - Se cache-statistikk

### Helsedata
- `GET /api/hrv` - HRV-data
- `GET /api/body-battery` - Body Battery data

## 🤖 MCP-lag for AI-coaching

Backend har et lokalt stdio-basert MCP-lag som gjør treningsdata tilgjengelig for Cursor, Claude Desktop og andre MCP-klienter.

Start serveren fra `backend`:

```bash
.venv/bin/python mcp_server.py
```

Eksempel på MCP-klientkonfigurasjon:

```json
{
  "mcpServers": {
    "treningsanalyse": {
      "command": "/home/erik-poppe/.openclaw/workspace/Treningsanalyse/backend/.venv/bin/python",
      "args": ["/home/erik-poppe/.openclaw/workspace/Treningsanalyse/backend/mcp_server.py"]
    }
  }
}
```

MCP-serveren er gradvis refaktorert til domene-moduler under `backend/app/mcp/tools/` (`profile`, `activities`, `routes`, `metrics`, `coaching`). `training_tools.py` er backwards-compatible facade.

MCP-serveren eksponerer blant annet:

- `athlete_profile` - profil, terskler, siste VO2max/HRV og datadekning
- `analyze_recent_training` - Banister, 80/20, terskel/drift og HRV-guidance
- `training_readiness_check` - praktisk vurdering av hard/moderat/rolig/hvile
- `list_recent_activities` - kompakt aktivitetsliste med eksplisitt dato/ukedag
- `activity_deep_dive` - fysiologi og kilometersplits
- `route_comparison` - sammenligning mot historiske samme-rute-løp
- `compare_recent_runs` - siste løp eller samme-rute-sammenligning
- `metric_catalog` - liste over whitelisted metrics som kan hentes
- `coaching_decision_snapshot` - consistency, event readiness, limiters, anbefalt økt
- `recommend_next_session` - neste økt med varighet, puls, begrunnelse, decision_trace og alternativ
- `classify_activity_session` - klassifiser løpeøkt (recovery, easy, threshold, intervals, race, …)
- `training_decision_brief` - kompakt AI-coaching-pakke via orchestrator (`detail=concise|standard|diagnostic`)
- `session_quality` / `comparable_sessions` - øktkvalitet og like-økt-benchmark
- `coaching_evaluation_report` - maskinlesbar modellvalidering (kalibrering, health, coverage)
- `query_metric_timeseries` - hent én metric som kompakt tidsserie

Resources:

- `treningsanalyse://athlete-profile`
- `treningsanalyse://coaching-snapshot`

## 🎯 Ytelse

Med automatisk beregning og intelligent caching:

- ⚡ 3-5x raskere sideinnlastning
- 📊 Ingen on-the-fly beregninger
- 🎨 Smooth brukeropplevelse
- 💾 Effektiv database-bruk

## 📊 Data som lagres

- **Aktiviteter:** 836+ aktiviteter fra 2011-2024
- **FIT-data:** 1,248,726+ datapunkter
- **HRV:** Data fra 2023+ (1010+ målinger)
- **Body Battery:** Daglige målinger
- **Training Effect:** Aerobic & Anaerobic

## 🛡️ Sikkerhet

- ✅ Credentials via `.env` (gitignore’t)
- ✅ CORS styrt av `CORS_ORIGINS`
- ✅ Sikkerhetsheaders (`X-Content-Type-Options`, `X-Frame-Options`, CSP, …)
- ✅ Maskert e-post i logger
- ✅ Garmin tokens i `TOKEN_DIR` (gitignore’t)

Se [docs/SECURITY.md](docs/SECURITY.md) for detaljer.

## 📝 Lisens

Personlig prosjekt - Ikke for kommersiell bruk

---

**Status:** ✅ Produksjonsklar  
**Siste oppdatering:** Juli 2026
