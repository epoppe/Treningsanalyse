# REPO_NOTES

Formålet med denne filen er å dokumentere trygge observasjoner om repoet uten å endre runtime-atferd.

## Faktisk appstruktur

Selv om repoet ser litt uoversiktlig ut på toppnivå, finnes det en relativt ryddig applikasjonskjerne.

### Backend-app
Hovedappen ligger under:
- `backend/app/`

Viktige deler:
- `backend/app/main.py` — FastAPI inngangspunkt
- `backend/app/routers/` — API-rutere
- `backend/app/services/` — domenelogikk og synk/analyseservice
- `backend/app/database/` — modeller og session-oppsett
- `backend/app/cache/` — cache-relatert kode
- `backend/app/middleware/` — middleware
- `backend/app/utils/` — hjelpeverktøy

### Frontend-app
Hovedfrontend ligger under:
- `frontend/src/`

Viktige deler:
- `frontend/src/app/` — Next.js app-ruter og sider
- `frontend/src/components/` — UI- og visualiseringskomponenter
- `frontend/src/hooks/` — klienthooks
- `frontend/src/store/` — state-håndtering
- `frontend/src/types/` — typer
- `frontend/src/utils/` — API/logging-hjelpere

## Observasjoner som er nyttige senere

### 1. Appkjernen virker ryddigere enn repo-roten
Det viktigste forbedringsbehovet ser ut til å være repo-organisering, ikke nødvendigvis at hovedappen er dårlig strukturert.

### 2. Backend har mange toppnivå-skript
`backend/` inneholder svært mange skript for:
- sjekk/debug
- migrering
- re-kalkulering
- engangsoperasjoner
- datasync

Dette bør sannsynligvis samles og kategoriseres senere, men ikke i en risikofri reiserunde.

### 3. Frontend har tegn til historisk duplisering
Det finnes:
- `frontend/package.json`
- `frontend/frontend/package.json`

Og også både:
- `frontend/next.config.js`
- `frontend/next.config.ts`

Dette bør undersøkes senere før opprydding, men er ikke rørt her.

### 4. Dokumentasjon må holdes konservativ
Det er tryggere å beskrive observert struktur enn å hevde at gamle dokumentfiler eller hjelpefiler fortsatt er aktive, med mindre det er verifisert.

## Trygg anbefaling for senere arbeid

Når tjenesten kan røres tryggere, er en god neste tekniske jobb:
1. kartlegge hvilke toppnivå-skript i `backend/` som fortsatt brukes
2. gruppere dem i `scripts/`-undermapper
3. rydde frontend-duplikater kontrollert
4. innføre noen få smoke tests for de viktigste flytene

## Viktig

Denne filen er ment som vedlikeholdsdokumentasjon.
Den skal ikke brukes som grunnlag for aggressive flyttinger uten en egen verifikasjonsrunde.
