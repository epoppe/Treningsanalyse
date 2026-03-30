# Treningsanalyse 🏃‍♂️

En webapplikasjon for analyse av treningsdata fra Garmin.

## ✨ Funksjoner

- 📊 Detaljert analyse av treningsaktiviteter
- ⚡ Automatisk synkronisering fra Garmin Connect
- 📈 Avanserte metrics: TSS, Power, Løpsøkonomi, Negative Split, Decoupling
- 💓 HRV og Body Battery tracking
- 📉 Training Stress og Recovery analyse
- 🎯 Ukentlige og månedlige sammendrag

## 🚀 Kom i gang

**Se `START_HERE.md` for oppstart og praktiske repo-notater.**

### Rask start

```bash
# 1. Konfigurer miljøvariabler
cd backend
copy env.example .env
# Rediger .env med Garmin-credentials og annen nødvendig config

# 2. Start backend
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Start frontend (ny terminal)
cd frontend
npm install
npm run dev
```

Åpne `http://localhost:3000`

## 🏗️ Teknologi

- **Frontend:** Next.js 14, React, TypeScript
- **Backend:** Python, FastAPI, SQLAlchemy
- **Database:** SQLite
- **Data:** Garmin Connect API, FIT-fil parsing

## 📚 Dokumentasjon

- **START_HERE.md** - trygg oppstart og repo-orientering
- **REPO_NOTES.md** - observerte strukturnotater og lavrisiko vedlikeholdsnotater
- **README.md** - kort prosjektoversikt

## 🔧 API-endepunkter

### Synkronisering
- `POST /api/sync/full-sync` - full synkronisering (aktiviteter + helsedata)
- `POST /api/sync/sync-new-activities` - synkroniser nye aktiviteter

### Aktiviteter
- `GET /api/activities` - hent aktiviteter
- `GET /api/activities/{id}` - hent spesifikk aktivitet
- `GET /api/activities/{id}/details` - hent FIT-data for aktivitet

### Cache / beregninger
- `POST /api/cache/calculate-all` - beregn manglende verdier
- `GET /api/cache/stats` - se cache-statistikk

### Helsedata
- `GET /api/hrv` - HRV-data
- `GET /api/body-battery` - Body Battery-data

## ⚠️ Repo-notater

Dette repoet ser ut til å være i aktiv bruk og inneholder også en del historiske eller operative hjelpefiler.

Derfor er denne første oppryddingsrunden bevisst konservativ:
- ingen runtime-kode er endret
- ingen databasefiler er rørt
- ingen scripts er flyttet eller slettet
- fokus er på trygg dokumentasjon og bedre orientering

## 🛡️ Sikkerhet

- bruk miljøvariabler for credentials
- ikke commit `.env`
- ikke legg hemmeligheter i repoet

## 📝 Lisens

Personlig prosjekt - ikke for kommersiell bruk

---

**Status:** aktivt prosjekt
