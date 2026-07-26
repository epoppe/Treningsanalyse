"""Lag 2 – normaliserte objekter.

Beregningskode skal konsumere Activity ORM + FitSeries (parquet),
ikke Garmin JSON-nøkler.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from .raw_access import materialize_fit_series_from_raw


@dataclass(frozen=True)
class NormalizedActivity:
    """Lesbar projeksjon av Activity for lag 3 (uten JSON-blob)."""

    activity_id: str
    start_time: Optional[datetime]
    distance: Optional[float]
    duration: Optional[float]
    average_speed: Optional[float]
    average_heart_rate: Optional[float]
    max_heart_rate: Optional[float]
    average_pace: Optional[float]
    epoc: Optional[float]
    vo2_max: Optional[float]
    vo2_max_precise: Optional[float]
    total_training_effect: Optional[float]
    temperature: Optional[float]
    has_fit_series: bool


def to_normalized_activity(activity: Any, *, has_fit_series: bool = False) -> NormalizedActivity:
    return NormalizedActivity(
        activity_id=str(activity.activity_id),
        start_time=getattr(activity, "start_time", None),
        distance=getattr(activity, "distance", None),
        duration=getattr(activity, "duration", None),
        average_speed=getattr(activity, "average_speed", None),
        average_heart_rate=getattr(activity, "average_heart_rate", None),
        max_heart_rate=getattr(activity, "max_heart_rate", None),
        average_pace=getattr(activity, "average_pace", None),
        epoc=getattr(activity, "epoc", None),
        vo2_max=getattr(activity, "vo2_max", None),
        vo2_max_precise=getattr(activity, "vo2_max_precise", None),
        total_training_effect=getattr(activity, "total_training_effect", None),
        temperature=getattr(activity, "temperature", None),
        has_fit_series=has_fit_series,
    )


def load_fit_series(
    activity_id: int,
    storage: Any,
    *,
    activity: Any = None,
    allow_raw_materialize: bool = True,
) -> Optional[pd.DataFrame]:
    """Last normalisert FIT-tidsserie (parquet).

    Ved manglende parquet kan engangs-materialisering fra raw JSON skje
    (lag 1 → 2), men kun via raw_access — ikke inline i beregningskode.
    """
    details_df = storage.get_activity_details(activity_id)
    if details_df is not None and not getattr(details_df, "empty", True):
        return details_df

    if not allow_raw_materialize or activity is None:
        return None

    raw = getattr(activity, "detailed_metrics", None)
    if raw is None:
        return None
    return materialize_fit_series_from_raw(activity_id, raw, storage)
