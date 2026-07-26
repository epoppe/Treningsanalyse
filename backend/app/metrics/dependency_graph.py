"""Avhengighetsgraf for avledede metrikker (lag 3).

Brukes til å vite:
- hvilke metrikker som må beregnes på nytt når kildedata endres
- hvilke cache-nøkler som skal invalideres etter omberegning

Kanoniske metric_key-verdier matcher metric_provenance / SyncMetricsService.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Iterable, List, Set

# Lag 2-inputs som beregninger leser (skalarer / FitSeries)
INPUT_NODES: FrozenSet[str] = frozenset(
    {
        "epoc",
        "distance",
        "duration",
        "average_speed",
        "average_heart_rate",
        "fit_series",
        "vo2_max",
    }
)

# metric_key → direkte avhengigheter (inputs eller andre metrikker)
METRIC_DEPENDENCIES: Dict[str, FrozenSet[str]] = {
    "training_stress_score": frozenset(
        {"epoc", "duration", "distance", "average_heart_rate"}
    ),
    "average_power": frozenset(
        {"distance", "duration", "average_speed", "fit_series"}
    ),
    "running_economy": frozenset({"average_speed", "average_heart_rate"}),
    "negative_split_percent": frozenset({"fit_series"}),
    "decoupling_percent": frozenset({"fit_series", "average_heart_rate"}),
    "avg_efficiency_factor": frozenset(
        {"average_power", "average_heart_rate", "fit_series"}
    ),
    "avg_grade_adjusted_speed": frozenset({"fit_series"}),
    "fatigue_resistance_score": frozenset(
        {"fit_series", "average_heart_rate", "average_speed"}
    ),
}

# CacheManager-typer som hører til metrikk (per aktivitet)
METRIC_TO_CACHE_TYPE: Dict[str, str] = {
    "training_stress_score": "tss",
    "average_power": "power",
}


def _reverse_edges() -> Dict[str, Set[str]]:
    reverse: Dict[str, Set[str]] = {}
    for metric, deps in METRIC_DEPENDENCIES.items():
        for dep in deps:
            reverse.setdefault(dep, set()).add(metric)
    return reverse


def dependents_of(changed: Iterable[str]) -> Set[str]:
    """Alle metrikker som direkte eller indirekte avhenger av `changed` noder."""
    reverse = _reverse_edges()
    pending = set(changed)
    affected: Set[str] = set()
    while pending:
        node = pending.pop()
        for metric in reverse.get(node, ()):
            if metric not in affected:
                affected.add(metric)
                pending.add(metric)
    return affected


def cache_types_for_metrics(metrics: Iterable[str]) -> Set[str]:
    """CacheManager-typer (tss/power/…) for et sett metrikker."""
    types: Set[str] = set()
    for metric in metrics:
        cache_type = METRIC_TO_CACHE_TYPE.get(metric)
        if cache_type:
            types.add(cache_type)
    return types


def invalidate_plan_for_changed_inputs(changed_inputs: Iterable[str]) -> Dict[str, Any]:
    """Plan for omberegning/invalidation når lag-2 inputs endres."""
    changed = set(changed_inputs)
    metrics = dependents_of(changed)
    return {
        "changed_inputs": sorted(changed),
        "metrics_to_recompute": sorted(metrics),
        "cache_types_to_invalidate": sorted(cache_types_for_metrics(metrics)),
    }


def topological_metrics() -> List[str]:
    """Metrikker i beregningsrekkefølge (avhengigheter først)."""
    remaining = set(METRIC_DEPENDENCIES)
    ordered: List[str] = []

    while remaining:
        # Klar når alle deps er INPUT eller allerede ordered
        ready = sorted(
            m
            for m in remaining
            if all(
                (d in INPUT_NODES) or (d in ordered)
                for d in METRIC_DEPENDENCIES[m]
            )
        )
        if not ready:
            # Syklus / uoppløst — dump resten stabilt
            ordered.extend(sorted(remaining))
            break
        for metric in ready:
            ordered.append(metric)
            remaining.remove(metric)
    return ordered
