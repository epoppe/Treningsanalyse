# Backend-skript

Kanoniske, vedlikeholdte skript ligger her. Engangs-/debug-skript på
`backend/`-roten er **legacy** og flyttes ikke automatisk (risiko for
ødelagte stier/vaner).

## Anbefalt (bruk disse)

### Synk / data
| Skript | Formål |
|--------|--------|
| `sync_activities_list.py` | Synk aktivitetsliste for periode |
| `sync_non_activity_data.py` | Helsedata uten aktiviteter |
| `run_garmin_performance_sync.py` | Garmin performance-metrikker |
| `download_fit_period.py` | Last ned FIT for periode |

### Backfill
| Skript | Formål |
|--------|--------|
| `backfill_activity_fields.py` | Aktivitetsfelter |
| `backfill_activity_data_validation.py` | Validering/repair |
| `backfill_derived_metrics.py` | Avledede metrikker |
| `backfill_grade_adjusted_speed.py` | Grade-adjusted speed |
| `backfill_garmin_weather.py` | Vær |
| `backfill_health_fields.py` | Helsedata |
| `backfill_summary_fields.py` | Sammendrag |

### Kvalitet / docs-generering
| Skript | Formål |
|--------|--------|
| `generate_metric_quality_report.py` | METRIC_QUALITY_REPORT |
| `generate_metric_glossary_md.py` | Ordliste |
| `generate_current_metrics_md.py` | MCP_CURRENT_METRICS |
| `generate_mcp_fresh_export.py` | MCP-eksport |
| `inspect_data_coverage.py` | Dekning |
| `portable_data_bundle.py` | Portabel datapakke |

### CI / smoke
| Skript | Formål |
|--------|--------|
| `preflight.sh` | Lokal smoke / guardrails |
| `ci_smoke_api.sh` | API-smoke for CI |

Kjøring typisk:

```bash
cd backend
.venv/bin/python scripts/<navn>.py --help
# eller
bash scripts/preflight.sh
```

## Legacy (backend/-roten)

~100 toppnivå-`.py`-filer (`check_*`, `debug_*`, `migrate_*`, engangs-recalc).
Disse er **ikke** del av app-oppstart (Alembic erstatter `migrate_*`).

Ved behov for opprydding senere:
1. Verifiser at ingen CI/docs/pakkefiler refererer skriptet
2. Flytt til `scripts/legacy/<kategori>/` i egen PR
3. Oppdater denne README

Se også `REPO_NOTES.md` i repo-roten.
