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

## 📚 Dokumentasjon

- **START_HERE.md** - Start her! Komplett guide og trygg oppstart
- **REPO_NOTES.md** - Struktur og lavrisiko vedlikeholdsnotater
- **docs/DATABASE_MIGRATIONS.md** - Alembic-migrasjoner
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

MCP-serveren eksponerer få, rike verktøy:

- `athlete_profile` - profil, terskler, siste VO2max/HRV og datadekning
- `analyze_recent_training` - Banister, 80/20, terskel/drift og HRV-guidance
- `training_readiness_check` - praktisk vurdering av hard/moderat/rolig/hvile
- `list_recent_activities` - kompakt aktivitetsliste med eksplisitt dato/ukedag
- `activity_deep_dive` - fysiologi og kilometersplits
- `route_comparison` - sammenligning mot historiske samme-rute-løp
- `compare_recent_runs` - siste løp eller samme-rute-sammenligning
- `metric_catalog` - liste over whitelisted metrics som kan hentes
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

- ✅ Miljøvariabler for credentials
- ✅ Ingen hardkodede passord
- ✅ Token-basert autentisering
- ✅ .env fil i .gitignore

## 📝 Lisens

Personlig prosjekt - Ikke for kommersiell bruk

---

**Status:** ✅ Produksjonsklar  
**Siste oppdatering:** Mai 2026
