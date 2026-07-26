# Metrikk-avhengighetsgraf

Avledede metrikker (lag 3) avhenger av normaliserte skalarer og FitSeries (lag 2).
Grafen brukes til omberegning og cache-invalidation.

```
Lag 2 inputs          →    Lag 3 metrikker
epoc, distance, …          TSS, power, EF, …
fit_series
```

## Kode

| Modul | Rolle |
|-------|--------|
| `app/metrics/dependency_graph.py` | Graf + `dependents_of` / `invalidate_plan_for_changed_inputs` |
| `app/cache/cache_manager.py` | `invalidate_activity(activity_id, cache_types=…)` |
| `SyncMetricsService` | Invaliderer TSS/power-cache etter vellykket metrics-commit |

## Eksempel

```python
from app.metrics import invalidate_plan_for_changed_inputs

plan = invalidate_plan_for_changed_inputs(["epoc", "fit_series"])
# metrics_to_recompute: TSS, power, splits, EF, …
# cache_types_to_invalidate: tss, power
```

## Regler

- Nye avledede metrikker skal legges inn i `METRIC_DEPENDENCIES`
- Proveniens-nøkler (`ALGORITHM_VERSIONS`) skal ha tilsvarende graf-node
- Cache-mapping (`METRIC_TO_CACHE_TYPE`) kun for metrikker som speiles i Redis/minne

## Tester

```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_metric_dependency_graph.py -v
```
