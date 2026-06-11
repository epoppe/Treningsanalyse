"""Beregning av grade-adjusted speed (GAP) fra FIT tidsserie (fart + høyde)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

MIN_VALID_SAMPLES = 20
MIN_GRADE_WINDOW_M = 5.0
DEFAULT_GRADE_WINDOW_M = 40.0
MAX_GRADE_FRACTION = 0.45
MIN_SPEED_MPS = 0.5
MAX_SPEED_MPS = 8.0
MAX_SAMPLE_DT_S = 15.0

# Minetti et al. 2002 — metabolsk kost (J·kg⁻¹·m⁻¹) for løp, flat referanse = 3.6.
_MINETTI_FLAT_COST = 3.6


def minetti_cost_factor(grade_fraction: float) -> float:
    """Metabolsk kost relativt flat mark for stigning g (rise/run som desimal)."""
    grade = float(grade_fraction)
    cost = (
        155.4 * grade**5
        - 30.4 * grade**4
        - 43.3 * grade**3
        + 46.3 * grade**2
        + 19.5 * grade
        + _MINETTI_FLAT_COST
    )
    return cost / _MINETTI_FLAT_COST


def _normalize_speed_mps(speed: pd.Series, reference_speed_mps: Optional[float] = None) -> pd.Series:
    """Normaliser FIT-fart til m/s (eldre data kan ha km/t)."""
    numeric = pd.to_numeric(speed, errors="coerce")
    positive = numeric[numeric > 0]
    if positive.empty:
        return numeric
    median = float(positive.median())
    if reference_speed_mps and reference_speed_mps > 0:
        ratio = median / reference_speed_mps
        if 2.2 <= ratio <= 4.5:
            return numeric / 3.6
    if median > 8:
        return numeric / 3.6
    return numeric


def _rolling_grade_fraction(
    distance_m: pd.Series,
    altitude_m: pd.Series,
    window_m: float,
) -> pd.Series:
    """Estimer stigning over et horisontalt vindu (reduserer barometer-støy)."""
    grades = np.full(len(distance_m), np.nan, dtype=float)
    dist = distance_m.to_numpy(dtype=float)
    alt = altitude_m.to_numpy(dtype=float)
    for idx in range(len(dist)):
        if not np.isfinite(dist[idx]) or not np.isfinite(alt[idx]):
            continue
        start_idx = idx
        while start_idx > 0 and np.isfinite(dist[start_idx - 1]):
            if dist[idx] - dist[start_idx - 1] >= window_m:
                break
            start_idx -= 1
        horizontal = dist[idx] - dist[start_idx]
        if horizontal < MIN_GRADE_WINDOW_M:
            continue
        vertical = alt[idx] - alt[start_idx]
        if not np.isfinite(vertical):
            continue
        grade = vertical / horizontal
        if abs(grade) <= MAX_GRADE_FRACTION:
            grades[idx] = grade
    return pd.Series(grades, index=distance_m.index)


@dataclass(frozen=True)
class GradeAdjustedSpeedResult:
    speed_mps: float
    sample_count: int
    method: str = "minetti_fit_timeseries"


def compute_avg_grade_adjusted_speed_mps(
    details_df: pd.DataFrame,
    *,
    reference_speed_mps: Optional[float] = None,
    grade_window_m: float = DEFAULT_GRADE_WINDOW_M,
) -> Optional[GradeAdjustedSpeedResult]:
    """
    Beregn snitt grade-adjusted speed (m/s) fra FIT/parquet med fart, høyde og distanse.

    Returnerer None når datagrunnlaget er for tynt eller mangler nødvendige kolonner.
    """
    if details_df is None or details_df.empty:
        return None

    required = {"timestamp", "speed", "distance", "altitude"}
    if not required.issubset(details_df.columns):
        return None

    work = details_df.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
    work = work.dropna(subset=["timestamp"]).sort_values("timestamp")
    if len(work) < MIN_VALID_SAMPLES:
        return None

    work["speed_mps"] = _normalize_speed_mps(work["speed"], reference_speed_mps)
    work["distance_m"] = pd.to_numeric(work["distance"], errors="coerce")
    work["altitude_m"] = pd.to_numeric(work["altitude"], errors="coerce")
    work["dt_s"] = work["timestamp"].diff().dt.total_seconds()
    work["grade"] = _rolling_grade_fraction(work["distance_m"], work["altitude_m"], grade_window_m)

    valid = (
        work["speed_mps"].between(MIN_SPEED_MPS, MAX_SPEED_MPS)
        & work["dt_s"].between(0, MAX_SAMPLE_DT_S)
        & work["grade"].notna()
    )
    samples = work.loc[valid]
    if len(samples) < MIN_VALID_SAMPLES:
        return None

    cost_factors = samples["grade"].map(minetti_cost_factor)
    gap_speed = samples["speed_mps"] * cost_factors
    weighted = float((gap_speed * samples["dt_s"]).sum() / samples["dt_s"].sum())
    if not np.isfinite(weighted) or weighted <= 0:
        return None

    return GradeAdjustedSpeedResult(
        speed_mps=round(weighted, 4),
        sample_count=int(len(samples)),
    )


def grade_adjusted_speed_from_fit_details(
    details_df: pd.DataFrame,
    *,
    reference_speed_mps: Optional[float] = None,
) -> Optional[float]:
    """Kompatibilitets-wrapper — returnerer bare m/s eller None."""
    result = compute_avg_grade_adjusted_speed_mps(
        details_df,
        reference_speed_mps=reference_speed_mps,
    )
    return result.speed_mps if result else None
