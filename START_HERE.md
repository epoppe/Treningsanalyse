# START_HERE

Dette er en trygg oppstarts- og orienteringsfil for repoet.

Målet er å gjøre det lettere å forstå prosjektet uten å endre runtime-atferd.

## Hva prosjektet er

Treningsanalyse er en webapplikasjon for analyse av Garmin-data, med:
- frontend i `frontend/`
- backend i `backend/`
- FastAPI i backend
- Next.js i frontend

## Viktige mapper

### `backend/`
Inneholder API, datalagring, synkronisering og mange vedlikeholds-/debugskript.

For appstart er det backend-appen under `backend/app/` som er hovedinngangen.

### `frontend/`
Inneholder Next.js-appen som brukes i normal utvikling.

Merk:
- det finnes også en liten ekstra mappe `frontend/frontend/`
- den ser ut til å være historisk eller duplisert
- den er **ikke** ryddet bort her for å unngå risiko mens tjenesten er i bruk

## Trygg oppstart lokalt

### Backend
```bash
cd backend
copy env.example .env
# fyll inn nødvendige miljøvariabler

# aktiver virtuelt miljø dersom det allerede finnes
.\.venv\Scripts\Activate.ps1

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend forventes normalt på:
- `http://localhost:3000`

Backend forventes normalt på:
- `http://localhost:8000`

## Viktige praktiske notater

- Ikke slett eller flytt debug-/migreringsskript uten en egen kontrollert oppryddingsrunde.
- Ikke rør `treningsanalyse.db` uten å vite hvordan databasen brukes i aktiv drift.
- Ikke anta at alle filer i repo-roten er aktive deler av appen; noen ser ut til å være historiske eller lokale hjelpefiler.

## Trygge forbedringer vs risikable forbedringer

### Trygge forbedringer
- README-forbedringer
- dokumentasjon
- strukturkommentarer
- tester som ikke påvirker drift
- små oppryddinger uten runtime-effekt

### Bør tas mer kontrollert
- flytting av backend-skript
- endring av runtime-konfig
- databaseendringer
- sync-logikk
- større frontend/backend-refaktorering

## Status på denne dokumentasjonen

Denne filen er opprettet for å gjøre repoet lettere å bruke og vedlikeholde uten å påvirke kjørende tjeneste.
