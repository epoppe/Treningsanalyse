"""Kontekstjusterte prestasjonstrender — unngår feilslutninger fra vær/terreng."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .metric_evidence import confidence_from_sample_count
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import SessionClassifierService
from .trend_analysis_service import TrendAnalysisService

HEAT_PENALTY_START_C = 18.0
HILL_ASCENT_PER_KM_M = 25.0


class ContextAdjustedTrendService:
    """Justerer EF/pace/drift-trender for elevation, vær, session type og rute."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
    ):
        self.db = db
        self.storage = storage
        self._trends = TrendAnalysisService(db, storage)
        self._classifier = SessionClassifierService(db, storage)
        self._ppap = PpapMetricsService(db, storage)

    def analyze_metric(
        self,
        metric: str,
        *,
        end_date: Optional[date] = None,
        window_days: int = 90,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        raw = self._trends.analyze_metric(metric, end_date=end, window_days=window_days)

        if metric not in {
            "easy_run_efficiency",
            "hr_drift",
            "decoupling",
            "lactate_threshold_pace",
        }:
            return {
                "metric": metric,
                "raw_trend": raw,
                "context_adjusted_trend": raw,
                "adjustments": [],
                "confidence": raw.get("confidence", 0.0),
                "note": "No context adjustment applied for this metric.",
            }

        series = self._context_series(metric, end - timedelta(days=window_days - 1), end)
        if len(series) < 3:
            return {
                "metric": metric,
                "raw_trend": raw,
                "context_adjusted_trend": {
                    **raw,
                    "direction": "uncertain",
                    "confidence": 0.2,
                },
                "adjustments": ["insufficient_contextualized_points"],
                "confidence": 0.2,
            }

        adjusted_values = [point["adjusted"] for point in series]
        adjustments = sorted({a for point in series for a in point.get("adjustments", [])})

        # Rebuild a simple trend on adjusted values
        current = adjusted_values[-1]
        baseline = sum(adjusted_values[: max(3, len(adjusted_values) // 4)]) / max(
            3,
            len(adjusted_values) // 4,
        )
        absolute_change = current - baseline
        relative = (absolute_change / baseline * 100) if baseline else None
        direction = self._direction(metric, relative)
        confidence = confidence_from_sample_count(len(adjusted_values))
        if adjustments:
            confidence *= 0.9

        adjusted_trend = {
            "metric": metric,
            "current": round(current, 4),
            "baseline": round(baseline, 4),
            "absolute_change": round(absolute_change, 4),
            "relative_change_pct": round(relative, 2) if relative is not None else None,
            "slope": raw.get("slope"),
            "direction": direction,
            "sample_count": len(adjusted_values),
            "confidence": round(confidence, 2),
            "start_date": raw.get("start_date"),
            "end_date": raw.get("end_date"),
            "context_adjusted": True,
        }

        return {
            "metric": metric,
            "raw_trend": raw,
            "context_adjusted_trend": adjusted_trend,
            "adjustments": adjustments,
            "confidence": round(confidence, 2),
            "points_used": len(adjusted_values),
        }

    def analyze_performance_bundle(
        self,
        *,
        end_date: Optional[date] = None,
        window_days: int = 90,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        metrics = ["easy_run_efficiency", "hr_drift", "decoupling"]
        return {
            "end_date": end.isoformat(),
            "window_days": window_days,
            "metrics": {
                metric: self.analyze_metric(metric, end_date=end, window_days=window_days)
                for metric in metrics
            },
        }

    def _context_series(
        self,
        metric: str,
        start: date,
        end: date,
    ) -> List[Dict[str, Any]]:
        column = {
            "easy_run_efficiency": "avg_efficiency_factor",
            "hr_drift": "hr_drift_pct",
            "decoupling": "decoupling_percent",
            "lactate_threshold_pace": None,
        }.get(metric)

        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .order_by(Activity.start_time)
            .all()
        )

        points: List[Dict[str, Any]] = []
        for activity in activities:
            if not is_running_activity(activity) or not activity.start_time:
                continue
            # Prefer easy sessions for efficiency/drift trends
            session_type = self._classifier.classify_activity(activity).get("session_type")
            if metric in {"easy_run_efficiency", "hr_drift", "decoupling"}:
                if session_type not in {"easy_aerobic", "long_aerobic", "recovery_run", "steady", "unknown"}:
                    continue

            raw_value = getattr(activity, column, None) if column else None
            if raw_value is None:
                continue

            adjusted, adjustments = self._adjust_value(float(raw_value), metric, activity)
            points.append(
                {
                    "date": activity.start_time.date().isoformat(),
                    "raw": float(raw_value),
                    "adjusted": adjusted,
                    "adjustments": adjustments,
                    "session_type": session_type,
                }
            )
        return points

    def _adjust_value(
        self,
        value: float,
        metric: str,
        activity: Activity,
    ) -> Tuple[float, List[str]]:
        adjustments: List[str] = []
        adjusted = value
        higher_is_worse = metric in {"hr_drift", "decoupling", "lactate_threshold_pace"}

        # Heat: worsens EF (lower) and increases drift
        if activity.temperature is not None and float(activity.temperature) > HEAT_PENALTY_START_C:
            heat = float(activity.temperature) - HEAT_PENALTY_START_C
            factor = min(0.15, heat * 0.01)
            if higher_is_worse:
                adjusted = adjusted * (1 - factor)  # remove heat-inflated drift
            else:
                adjusted = adjusted / (1 - factor) if factor < 1 else adjusted  # restore EF
            adjustments.append(f"heat_adjustment_temp={activity.temperature}")

        if activity.humidity is not None and float(activity.humidity) > 75:
            factor = min(0.08, (float(activity.humidity) - 75) * 0.004)
            if higher_is_worse:
                adjusted = adjusted * (1 - factor)
            else:
                adjusted = adjusted / (1 - factor) if factor < 1 else adjusted
            adjustments.append(f"humidity_adjustment={activity.humidity}")

        # Hilly: ascent per km
        if activity.total_ascent and activity.distance and float(activity.distance) > 0:
            ascent_per_km = float(activity.total_ascent) / (float(activity.distance) / 1000.0)
            if ascent_per_km > HILL_ASCENT_PER_KM_M:
                factor = min(0.12, (ascent_per_km - HILL_ASCENT_PER_KM_M) / 200.0)
                if higher_is_worse:
                    adjusted = adjusted * (1 - factor)
                else:
                    adjusted = adjusted / (1 - factor) if factor < 1 else adjusted
                adjustments.append(f"elevation_adjustment_ascent_per_km={ascent_per_km:.1f}")

        if activity.activity_type and activity.activity_type.type_key in {
            "treadmill_running",
            "indoor_running",
        }:
            adjustments.append("treadmill_context")

        return adjusted, adjustments

    @staticmethod
    def _direction(metric: str, relative_change_pct: Optional[float]) -> str:
        if relative_change_pct is None:
            return "uncertain"
        higher_is_better = metric not in {"hr_drift", "decoupling", "lactate_threshold_pace"}
        if abs(relative_change_pct) < 3:
            return "stable"
        improving = relative_change_pct > 0 if higher_is_better else relative_change_pct < 0
        return "improving" if improving else "declining"
