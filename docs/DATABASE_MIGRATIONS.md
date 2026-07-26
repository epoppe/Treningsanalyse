# Database-migrasjoner (Alembic)

Treningsanalyse bruker [Alembic](https://alembic.sqlalchemy.org/) for schema-versjonering.

## Hurtigstart

Fra `backend/`:

```bash
# Opprett / oppgrader database til siste schema
alembic upgrade head

# Vis gjeldende revisjon
alembic current

# Generer ny migrasjon etter modellendring
alembic revision --autogenerate -m "beskrivelse"
```

Ved app-oppstart kjøres `alembic upgrade head` automatisk
(se `app/database/migrations.py` og `app/main.py`).

## Ny database

```bash
cd backend
alembic upgrade head
# eller
python init_database.py   # migrasjon + seed av aktivitetstyper
```

## Eksisterende database (pre-Alembic)

Databaser som tidligere ble opprettet med `Base.metadata.create_all()` og
manuelle `migrate_*.py`-skript har ikke `alembic_version`-tabell.

Ved første oppstart etter denne endringen:

1. Systemet detekterer eksisterende app-tabeller uten Alembic-versjon
2. Schema stemples til `head` (**uten datatap**)
3. Deretter kjøres `upgrade head` (no-op hvis allerede på head)

De gamle `backend/migrate_*.py`-skriptene kalles ikke lenger ved oppstart.
De beholdes midlertidig som referanse/legacy.

## Health check

`GET /health` returnerer:

```json
{
  "status": "ok",
  "schema_version": "2e6ad7447506",
  "schema_head": "2e6ad7447506",
  "schema_at_head": true
}
```

## Viktige filer

| Fil | Rolle |
|-----|--------|
| `backend/alembic.ini` | Alembic-konfigurasjon |
| `backend/alembic/env.py` | Kobler modeller + DATABASE_URL |
| `backend/alembic/versions/` | Migrasjonsskript |
| `backend/app/database/migrations.py` | Programmatisk upgrade/stamp |
| `backend/app/database/models/` | SQLAlchemy-modeller (kilde til truth) |

## Regler

- Ikke bruk `Base.metadata.create_all()` i produksjonsoppstart.
- Etter modellendring: generer migrasjon, review, commit.
- SQLite bruker `render_as_batch=True` (nødvendig for ALTER).
- Aldri rediger allerede anvendte migrasjoner — lag en ny.

## SyncRun / sync_lock

Migrasjon `a0aa219a0c49` legger til:

- `sync_runs` — audit/statistikk per synk-kjøring
- `sync_locks` — global eksklusiv synk-lås

API (additivt, bakoverkompatibelt):

- `GET /api/sync/runs`
- `GET /api/sync/lock`
