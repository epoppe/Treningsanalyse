from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import math

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..database.models.activity import Activity
from ..database.models.sleep import HRV, Sleep
from ..database.models.body_battery import BodyBattery
from ..database.models.stress import Stress

router = APIRouter(tags=["Factor Relationships"])

METRICS: Dict[str, Dict[str, str]] = {
    "distance": {"source": "activity", "label": "Distanse", "unit": "km"},
    "duration": {"source": "activity", "label": "Varighet", "unit": "min"},
    "average_hr": {"source": "activity", "label": "Snittpuls", "unit": "bpm"},
    "average_power": {"source": "activity", "label": "Snitteffekt", "unit": "W"},
    "training_stress_score": {"source": "activity", "label": "TSS", "unit": "score"},
    "epoc": {"source": "activity", "label": "EPOC", "unit": "load"},
    "total_training_effect": {"source": "activity", "label": "Aerob treningseffekt", "unit": "score"},
    "total_anaerobic_training_effect": {"source": "activity", "label": "Anaerob treningseffekt", "unit": "score"},
    "negative_split_percent": {"source": "activity", "label": "Negative split", "unit": "%"},
    "decoupling_percent": {"source": "activity", "label": "Decoupling", "unit": "%"},
    "training_readiness_score": {"source": "activity", "label": "Training readiness", "unit": "score"},
    "body_battery_start": {"source": "activity", "label": "Body Battery start", "unit": "score"},
    "sleep_score": {"source": "health", "label": "Søvnskår", "unit": "score"},
    "sleep_time": {"source": "health", "label": "Søvnlengde", "unit": "timer"},
    "hrv": {"source": "health", "label": "HRV", "unit": "ms"},
    "body_battery": {"source": "health", "label": "Body Battery", "unit": "score"},
    "stress_avg": {"source": "health", "label": "Stress", "unit": "score"},
}


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def _first_present_float(obj: Any, attr_names: List[str]) -> Optional[float]:
    for name in attr_names:
        v = _safe_float(getattr(obj, name, None))
        if v is not None:
            return v
    return None


def _avg_hrv_by_measurement_date(rows: List[HRV]) -> Dict[date, float]:
    sums: Dict[date, float] = defaultdict(float)
    counts: Dict[date, int] = defaultdict(int)
    for row in rows:
        d = row.measurement_date
        if d is None:
            continue
        v = _safe_float(getattr(row, "rmssd", None))
        if v is None:
            continue
        sums[d] += v
        counts[d] += 1
    return {d: sums[d] / counts[d] for d in sums if counts[d] > 0}


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) < 3 or len(ys) < 3:
        return None
    try:
        corr = float(np.corrcoef(xs, ys)[0, 1])
        if math.isnan(corr):
            return None
        return corr
    except Exception:
        return None


def _avg(values: List[Optional[float]]) -> Optional[float]:
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    return float(sum(cleaned) / len(cleaned))


@router.get("/factor-relationships")
def get_factor_relationships(
    x_metric: str = Query("sleep_score"),
    y_metric: str = Query("training_stress_score"),
    days: int = Query(90, ge=14, le=365),
    activity_type: Optional[str] = Query(None),
    min_distance_km: float = Query(0.0, ge=0.0),
    db: Session = Depends(get_db),
):
    if x_metric not in METRICS or y_metric not in METRICS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unknown_metric",
                "allowed_metrics": list(METRICS.keys()),
            },
        )

    start_dt = datetime.now() - timedelta(days=days)
    lookback_day = start_dt.date() - timedelta(days=1)
    activities_query = db.query(Activity).filter(Activity.start_time >= start_dt)
    if activity_type:
        activities_query = activities_query.join(Activity.activity_type).filter_by(type_key=activity_type)

    activities = activities_query.order_by(Activity.start_time.asc()).all()

    sleep_rows = db.query(Sleep).filter(Sleep.sleep_date >= lookback_day).all()
    sleep_by_date = {row.sleep_date: row for row in sleep_rows}

    hrv_rows = db.query(HRV).filter(HRV.measurement_date >= lookback_day).all()
    hrv_by_date = _avg_hrv_by_measurement_date(hrv_rows)

    bb_rows = db.query(BodyBattery).filter(BodyBattery.date >= lookback_day).all()
    bb_by_date = {row.date: row for row in bb_rows}

    stress_rows = db.query(Stress).filter(Stress.stress_date >= lookback_day).all()
    stress_by_date = {row.stress_date: row for row in stress_rows}

    def metric_value(metric: str, activity: Activity) -> Optional[float]:
        activity_day = activity.start_time.date() if activity.start_time else None
        if activity_day is None:
            return None
        prev_day = activity_day - timedelta(days=1)

        if metric == "distance":
            return _safe_float((activity.distance or 0) / 1000.0) if activity.distance is not None else None
        if metric == "duration":
            return _safe_float((activity.duration or 0) / 60.0) if activity.duration is not None else None
        if metric == "average_hr":
            return _safe_float(activity.average_heart_rate)
        if metric == "average_power":
            return _safe_float(activity.average_power)
        if metric == "training_stress_score":
            return _safe_float(activity.training_stress_score)
        if metric == "epoc":
            return _safe_float(activity.epoc)
        if metric == "total_training_effect":
            return _safe_float(activity.total_training_effect)
        if metric == "total_anaerobic_training_effect":
            return _safe_float(activity.total_anaerobic_training_effect)
        if metric == "negative_split_percent":
            return _safe_float(activity.negative_split_percent)
        if metric == "decoupling_percent":
            return _safe_float(activity.decoupling_percent)
        if metric == "training_readiness_score":
            return _safe_float(activity.training_readiness_score)
        if metric == "body_battery_start":
            return _safe_float(activity.body_battery_start)
        if metric == "sleep_score":
            row = sleep_by_date.get(prev_day)
            if row is None:
                return None
            return _first_present_float(
                row,
                ["sleep_score", "overall_score", "recovery_score"],
            )
        if metric == "sleep_time":
            row = sleep_by_date.get(prev_day)
            if row is None:
                return None
            total_sleep_time = getattr(row, "total_sleep_time", None)
            if total_sleep_time is None:
                return None
            return _safe_float(total_sleep_time / 3600.0)
        if metric == "hrv":
            v = hrv_by_date.get(prev_day)
            if v is not None:
                return v
            sleep_row = sleep_by_date.get(prev_day)
            if sleep_row is None:
                return None
            return _safe_float(getattr(sleep_row, "heart_rate_variability", None))
        if metric == "body_battery":
            row = bb_by_date.get(prev_day)
            if row is None:
                return None
            return _first_present_float(
                row,
                [
                    "max_body_battery",
                    "body_battery_charged",
                    "body_battery_charged_start",
                    "min_body_battery",
                ],
            )
        if metric == "stress_avg":
            row = stress_by_date.get(prev_day)
            if row is None:
                return None
            return _first_present_float(row, ["stress_level"])
        return None

    points: List[Dict[str, Any]] = []
    x_vals: List[float] = []
    y_vals: List[float] = []

    for activity in activities:
        distance_km = (activity.distance or 0) / 1000.0 if activity.distance else 0.0
        if distance_km < min_distance_km:
            continue
        x_val = metric_value(x_metric, activity)
        y_val = metric_value(y_metric, activity)
        if x_val is None or y_val is None:
            continue
        x_vals.append(x_val)
        y_vals.append(y_val)
        points.append({
            "activity_id": activity.activity_id,
            "activity_name": activity.activity_name,
            "activity_type": getattr(activity.activity_type, "type_key", None),
            "date": activity.start_time.date().isoformat() if activity.start_time else None,
            "x": round(x_val, 3),
            "y": round(y_val, 3),
            "distance_km": round(distance_km, 2),
            "duration_min": round((activity.duration or 0) / 60.0, 1) if activity.duration else None,
        })

    corr = _pearson(x_vals, y_vals)
    strength = "insufficient"
    if corr is not None:
        abs_corr = abs(corr)
        if abs_corr >= 0.7:
            strength = "strong"
        elif abs_corr >= 0.4:
            strength = "moderate"
        elif abs_corr >= 0.2:
            strength = "weak"
        else:
            strength = "very weak"

    avg_x = _avg(x_vals)
    avg_y = _avg(y_vals)

    return {
        "x_metric": x_metric,
        "y_metric": y_metric,
        "days": days,
        "activity_type": activity_type,
        "point_count": len(points),
        "correlation": round(corr, 4) if corr is not None else None,
        "correlation_strength": strength,
        "x_meta": METRICS[x_metric],
        "y_meta": METRICS[y_metric],
        "summary": {
            "avg_x": round(avg_x, 3) if avg_x is not None else None,
            "avg_y": round(avg_y, 3) if avg_y is not None else None,
        },
        "available_metrics": METRICS,
        "points": points,
    }
