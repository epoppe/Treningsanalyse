# Database portability — SQLite today, Postgres later

**Current production desktop database:** SQLite  
**ORM / migrations:** SQLAlchemy + Alembic  
**Config surface:** `settings.DATABASE_URL` (`backend/app/config.py`)

This document lists SQLite-specific assumptions so a future Postgres migration can be a focused project rather than an architectural rewrite.

---

## What is already portable

| Area | Status |
|------|--------|
| SQLAlchemy models | Generally portable |
| Alembic migrations | `render_as_batch` only for SQLite |
| Engine factory | Branches on `sqlite` vs other (`session.py`) |
| Settings | Accepts any SQLAlchemy URL |
| Health probes | Use dialect-neutral `SELECT 1` |

Desktop and MCP both consume the same `DATABASE_URL`.

---

## Known SQLite-specific couplings

1. **PRAGMAs** — WAL, busy_timeout, foreign_keys, cache_size (isolated in `configure_sqlite`)
2. **NullPool** for SQLite (threadpool safety)
3. **Partial indexes** — `sqlite_where=` on some `Activity` indexes
4. **`sqlite_autoincrement`** table args on summary models
5. **Widespread `func.date(...)`** — works on both dialects but indexing/perf differs
6. **File-level backup / import** — `sqlite_backup.py`, desktop AppData `.db` copy
7. **Legacy scripts** under `backend/migrate_*.py` using raw `sqlite3` + `PRAGMA table_info` (not production path)

---

## Estimated Postgres migration complexity

**Medium** for a single-user→server move:

1. Provision Postgres and set `DATABASE_URL=postgresql+psycopg://…`
2. Replace / dual-path partial indexes and `sqlite_autoincrement`
3. Re-validate `func.date` filters and timezone handling
4. Replace file backup with `pg_dump` (or logical export)
5. Update desktop packaging (Postgres is a **different product** — not a drop-in for offline single-user)

**Not recommended for the local desktop SKU** — keep SQLite there.

---

## Recommended migration sequence (future project)

1. Add CI job that runs Alembic + a subset of API tests against Postgres
2. Fix model/index dialect differences behind helpers
3. Document ops (backup, connection pool, migrations)
4. Optional: hosted multi-user deployment — **separate** from Windows desktop

---

## Desktop SQLite locations (Windows)

```text
%LOCALAPPDATA%\Treningsanalyse\
  data\treningsanalyse.db
  tokens\
  fit\
  cache\
  logs\
  backups\
  config\
```

Override root with `TRAININGSANALYSE_DATA_DIR`.
