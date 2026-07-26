"""Lag 1 – råtilgang.

Kun sync/ingest og engangs-materialisering til parquet skal bruke dette.
Beregningskode (lag 3) skal kalle layers.normalized.load_fit_series i stedet.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _coerce_dict(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _extract_records(details: Dict[str, Any]) -> Optional[List[Any]]:
    candidate_lists = [
        details.get("records"),
        details.get("fit_records"),
        details.get("samples"),
    ]
    for key in ("fit_data", "metrics", "data"):
        container = details.get(key)
        if isinstance(container, dict):
            candidate_lists.extend(
                [
                    container.get("records"),
                    container.get("fit_records"),
                    container.get("samples"),
                ]
            )
    for candidate in candidate_lists:
        if isinstance(candidate, list) and candidate:
            return candidate
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_raw_fit_records_to_dataframe(detailed_metrics: Any) -> Optional[pd.DataFrame]:
    """Konverter Activity.detailed_metrics (rå FIT-JSON) til tidsserie-DataFrame."""
    details = _coerce_dict(detailed_metrics)
    if not details:
        return None

    records = _extract_records(details)
    if not records:
        return None

    parsed_records: List[Dict[str, Any]] = []
    synthetic_index = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        timestamp = pd.to_datetime(
            record.get("timestamp")
            or record.get("time")
            or record.get("record_timestamp"),
            errors="coerce",
        )
        speed = _to_float(
            record.get("enhanced_speed")
            or record.get("speed")
            or record.get("enhancedSpeed")
        )
        heart_rate = _to_float(
            record.get("heart_rate")
            or record.get("heartrate")
            or record.get("hr")
        )
        distance = _to_float(
            record.get("distance")
            or record.get("enhanced_distance")
            or record.get("enhancedDistance")
        )
        altitude = _to_float(
            record.get("altitude")
            or record.get("enhanced_altitude")
            or record.get("enhancedAltitude")
        )
        cadence = _to_float(record.get("cadence"))
        latitude = _to_float(record.get("position_lat") or record.get("latitude"))
        longitude = _to_float(record.get("position_long") or record.get("longitude"))
        temperature = _to_float(record.get("temperature"))

        has_metrics = any(
            v is not None
            for v in (
                speed,
                heart_rate,
                distance,
                altitude,
                cadence,
                latitude,
                longitude,
                temperature,
            )
        )
        if not has_metrics:
            continue

        # Tillat records uten timestamp for aggregater (f.eks. max HR).
        if pd.isna(timestamp):
            timestamp = pd.Timestamp("1970-01-01", tz="UTC") + pd.Timedelta(
                synthetic_index, unit="s"
            )
            synthetic_index += 1

        parsed_records.append(
            {
                "timestamp": timestamp,
                "speed": speed,
                "heart_rate": heart_rate,
                "distance": distance,
                "altitude": altitude,
                "cadence": cadence,
                "latitude": latitude,
                "longitude": longitude,
                "temperature": temperature,
            }
        )

    if not parsed_records:
        return None
    return pd.DataFrame(parsed_records)


def materialize_fit_series_from_raw(
    activity_id: int,
    detailed_metrics: Any,
    storage: Any,
) -> Optional[pd.DataFrame]:
    """Materialiser rå FIT-JSON til parquet (lag 1 → lag 2) og returner serien.

    Idempotent: hvis parquet allerede har data, returneres den uten omskriving.
    """
    existing = storage.get_activity_details(activity_id)
    if existing is not None and not getattr(existing, "empty", True):
        return existing

    df = parse_raw_fit_records_to_dataframe(detailed_metrics)
    if df is None or df.empty:
        return None

    try:
        records = []
        for _, row in df.iterrows():
            records.append(
                {
                    "activity_id": int(activity_id),
                    "timestamp": row.get("timestamp"),
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "distance": row.get("distance"),
                    "speed": row.get("speed"),
                    "heart_rate": row.get("heart_rate"),
                    "cadence": row.get("cadence"),
                    "temperature": row.get("temperature"),
                    "altitude": row.get("altitude"),
                }
            )
        if records:
            storage.save_activity_details(records, replace_activity_ids=[int(activity_id)])
            logger.info(
                "Materialiserte %s FIT-records fra raw JSON → parquet for aktivitet %s",
                len(records),
                activity_id,
            )
    except Exception as exc:
        logger.warning(
            "Kunne ikke materialisere FIT-JSON til parquet for %s: %s",
            activity_id,
            exc,
        )
        return df

    refreshed = storage.get_activity_details(activity_id)
    if refreshed is not None and not getattr(refreshed, "empty", True):
        return refreshed
    return df
