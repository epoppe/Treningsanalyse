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
- migrering (legacy `migrate_*.py` — ikke lenger kalt ved oppstart)
- re-kalkulering
- engangsoperasjoner
- datasync

Schema-migrasjoner håndteres nå av Alembic (`backend/alembic/`, se `docs/DATABASE_MIGRATIONS.md`).
Øvrige toppnivå-skript bør sannsynligvis samles og kategoriseres senere.

### 3. Frontend-duplikater (status juli 2026)
Tidligere fantes tegn på `frontend/frontend/` og dobbel `next.config`.
Per nå: kun `frontend/package.json` + `frontend/next.config.js`.
`npm run lint` og `npm run build` er grønne.

### 4. Dokumentasjon må holdes konservativ
Det er tryggere å beskrive observert struktur enn å hevde at gamle dokumentfiler eller hjelpefiler fortsatt er aktive, med mindre det er verifisert.

## Trygg anbefaling for senere arbeid

### Scripts
Kanoniske skript er dokumentert i `backend/scripts/README.md`.
Toppnivå-`check_*` / `debug_*` / `migrate_*` er legacy (ikke mass-flyttet).

Robusthetsstatus: `docs/ROBUSTNESS_STATUS.md`.

Når tjenesten kan røres tryggere videre:
1. flytt verifiserte legacy-skript til `scripts/legacy/<kategori>/` i egne PR-er
2. utvid smoke/guardrail-tester der det mangler
3. vurder nettverksauth foran API hvis eksponert utenfor localhost

## Viktig

Denne filen er ment som vedlikeholdsdokumentasjon.
Den skal ikke brukes som grunnlag for aggressive flyttinger uten en egen verifikasjonsrunde.
