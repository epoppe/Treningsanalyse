# Tre datalag

Treningsanalyse skiller data i tre lag:

```
Raw Garmin / FIT          (lag 1)
        ↓
Normaliserte objekter     (lag 2)  — Activity ORM + parquet FitSeries
        ↓
Avledede metrikker        (lag 3)  — TSS, power, EF, decoupling, …
```

## Regel

**Beregningskode (lag 3) skal ikke lese Garmin JSON direkte.**

Tillatt i lag 3:
- `Activity`-kolonner (skalarer)
- FitSeries via `layers.normalized.load_fit_series` (parquet)

Ikke tillatt i lag 3:
- `activity.detailed_metrics`
- `summaryDTO` / camelCase Garmin-nøkler (`averageHR`, `enhanced_speed`, …)

## Moduler

| Lag | Kode |
|-----|------|
| 1 Raw | `app/layers/raw_access.py`, sync/FIT-import |
| 2 Normalisert | `app/layers/normalized.py`, `Activity`, parquet |
| 3 Avledet | `analysis_service`, `metrics_service`, `power_service`, PPAP/MCP |

## Grensekontroll

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_layer_boundaries.py -v
```

`scan_derived_layer_violations` feiler CI hvis lag 3-moduler igjen leser Garmin JSON.
