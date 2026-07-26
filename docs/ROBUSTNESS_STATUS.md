# Robusthet og effektivisering (v2) — status

Sluttevaluering av arbeidslisten uten nye features.

## Fullført

### Fase 1 — Fundament
| Punkt | Status | PR / merknad |
|-------|--------|----------------|
| Alembic-migrasjoner | ✅ | Schema-versjon i `/health` |
| GitHub Actions CI | ✅ | Lint/tsc/build + pytest-subset |
| SyncRun + synk-lås | ✅ | Audit + eksklusiv lock |

### Fase 2 — Data
| Punkt | Status | PR / merknad |
|-------|--------|----------------|
| insert/update/unchanged | ✅ | `activity_upsert` |
| Dataintegritet / health | ✅ | `/health/live\|ready\|data` |
| Dataproveniens | ✅ | `metric_provenance` |
| Tre datalag | ✅ | `app/layers/`, `docs/DATA_LAYERS.md` |

### Fase 3 — Synk
| Punkt | Status | PR / merknad |
|-------|--------|----------------|
| Bryt opp SyncService | ✅ | activity / performance / weather / FIT / helse |
| Fjern `asyncio.run()` | ✅ | Guardrail-test |
| Batch commits (100) | ✅ | + parquet flush |
| Restartbar synk / checkpoint | ✅ | SyncState + `SyncRun.checkpoint` |

`SyncService` er nå ~326 linjer (coordinator).

### Fase 4 — SQL
| Punkt | Status | PR / merknad |
|-------|--------|----------------|
| Query-/FK-indekser | ✅ | `d4b2e8c17a01`, delvis TE-indeks |

### Fase 5–7 — Metrikker / cache / config
| Punkt | Status | PR / merknad |
|-------|--------|----------------|
| Dependency graph | ✅ | `app/metrics/`, `docs/METRIC_DEPENDENCIES.md` |
| Cache-invalidation | ✅ | per aktivitet etter metrics-commit |
| Settings-konsolidering | ✅ | ren pydantic-settings |

### Fase 8+ — Sikkerhet / scripts / frontend
| Punkt | Status | PR / merknad |
|-------|--------|----------------|
| CORS + security headers | ✅ | `docs/SECURITY.md` |
| Scripts-katalog | ✅ | `backend/scripts/README.md` (uten mass-flytting) |
| Frontend lint/build | ✅ | `npm run lint` / `npm run build` grønt |

## Bevisst utsatt / begrenset

- **Mass-flytting av ~100 legacy-skript** på `backend/`-roten — dokumentert, ikke flyttet (risiko)
- **API-brukerauth** — personlig app; nettverksbeskyttelse anbefales (se SECURITY.md)
- **Kjente røde tester** i full suite (performance-metrics m.fl.) — pre-eksisterende, ikke regresjon fra denne listen

## Verifikasjon (lokal)

```bash
# Backend guardrails / subset
cd backend && PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_alembic_migrations.py \
  tests/test_layer_boundaries.py \
  tests/test_metric_dependency_graph.py \
  tests/test_security_headers.py \
  tests/test_settings.py \
  tests/test_sync_checkpoint.py \
  tests/test_sync_batch_commits.py -q

# Frontend
cd frontend && npm run lint && npm run build
```

## Prinsipper fulgt

- Ingen features — kun robusthet/vedlikehold/ytelse
- Små isolerte PR-er, bakoverkompatible API-er
- Tester med større endringer
