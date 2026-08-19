"""Longitudinal trend-analyse for coaching-metrikker med robuste estimater."""

from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import median
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .coaching_decision_metrics_service import CoachingDecisionMetricsService
from .metric_evidence import confidence_from_sample_count
from .mcp_derived_metrics_service import McpDerivedMetricsService
from .ppap_metrics_service import PpapMetricsService

TrendDirection = str  # improving|stable|declining|uncertain

TREND_WINDOWS_DAYS = (7, 28, 90, 365)

MIN_SAMPLES_FOR_SLOPE = 5
MIN_SAMPLES_FOR_DIRECTION = 3
CHANGE_POINT_Z_THRESHOLD = 2.0
STABLE_RELATIVE_CHANGE_PCT = 3.0

METRIC_FETCHERS: Dict[str, str] = {
    "vo2max": "__custom_vo2max__",
    "lactate_threshold_hr": "__custom_lt_hr__",
    "lactate_threshold_pace": "__custom_lt_pace__",
    "easy_run_efficiency": "fitness.ef_30d",
    "hr_drift": "cardio.drift_score",
    "decoupling": "__custom_decoupling__",
    "critical_speed": "running.critical_speed",
    "ctl": "fitness.ctl",
    "resting_hr": "cardio.rhr_7d",
    "hrv_rmssd": "cardio.hrv_7d",
    "sleep_score": "__custom_sleep__",
    "durability": "__custom_durability__",
}


class TrendAnalysisService:
    """Analyserer utvikling over tid for nøkkelmetrikker uten fremtidslekkasje."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        derived: Optional[McpDerivedMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._derived = derived or McpDerivedMetricsService(db, storage)
        self._ppap = self._derived._ppap

    def analyze_metric(
        self,
        metric: str,
        *,
        end_date: Optional[date] = None,
        window_days: int = 28,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        start = end - timedelta(days=window_days - 1)
        series = self._fetch_series(metric, start, end)
        return self._compute_trend(metric, series, start, end, window_days)

    def analyze_all(
        self,
        *,
        end_date: Optional[date] = None,
        windows: Tuple[int, ...] = TREND_WINDOWS_DAYS,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        trends: Dict[str, Dict[str, Any]] = {}
        for metric in METRIC_FETCHERS:
            trends[metric] = {}
            for window in windows:
                if not self._window_applicable(metric, window):
                    continue
                trends[metric][f"{window}d"] = self.analyze_metric(
                    metric,
                    end_date=end,
                    window_days=window,
                )
        return {
            "end_date": end.isoformat(),
            "windows_days": list(windows),
            "metrics": trends,
        }

    def _window_applicable(self, metric: str, window_days: int) -> bool:
        if window_days == 365 and metric in {"hrv_rmssd", "sleep_score"}:
            return True
        if window_days == 7 and metric in {"critical_speed", "vo2max", "durability"}:
            return False
        return True

    def _fetch_series(
        self,
        metric: str,
        start: date,
        end: date,
    ) -> List[Tuple[date, float]]:
        custom = {
            "durability": self._durability_series,
            "decoupling": lambda s, e: self._activity_metric_series(s, e, "decoupling_percent"),
            "easy_run_efficiency": lambda s, e: self._activity_metric_series(s, e, "avg_efficiency_factor"),
            "lactate_threshold_hr": lambda s, e: self._lt_series(s, e, "hr"),
            "lactate_threshold_pace": lambda s, e: self._lt_series(s, e, "pace"),
            "vo2max": self._vo2max_series,
            "sleep_score": self._sleep_score_series,
        }
        if metric in custom:
            return custom[metric](start, end)

        metric_key = METRIC_FETCHERS.get(metric)
        if not metric_key or metric_key.startswith("__custom"):
            return []

        definition = self._derived.metric_definition(metric_key)
        if definition and definition.get("scope") == "snapshot":
            return self._daily_value_series(metric_key, start, end)

        result = self._derived.query_timeseries(
            metric_key,
            start_date=start,
            end_date=end,
            limit=(end - start).days + 1,
        )
        points: List[Tuple[date, float]] = []
        for point in result.get("points", []):
            day_str = point.get("date") or point.get("activity_date")
            value = point.get("value")
            if day_str is None or value is None:
                continue
            try:
                day = date.fromisoformat(str(day_str)[:10])
                points.append((day, float(value)))
            except (TypeError, ValueError):
                continue
        points.sort(key=lambda item: item[0])
        return points

    def _daily_value_series(
        self,
        metric_key: str,
        start: date,
        end: date,
    ) -> List[Tuple[date, float]]:
        points: List[Tuple[date, float]] = []
        current = start
        while current <= end:
            value = self._derived._daily_metric_value(metric_key, current)
            if value is not None:
                points.append((current, float(value)))
            current += timedelta(days=1)
        return points

    def _vo2max_series(self, start: date, end: date) -> List[Tuple[date, float]]:
        from sqlalchemy import and_

        from ..database.models.activity import GarminPerformanceMetric

        rows = (
            self.db.query(GarminPerformanceMetric.date, GarminPerformanceMetric.vo2_max_precise)
            .filter(
                and_(
                    GarminPerformanceMetric.date >= start,
                    GarminPerformanceMetric.date <= end,
                    GarminPerformanceMetric.vo2_max_precise.isnot(None),
                )
            )
            .order_by(GarminPerformanceMetric.date)
            .all()
        )
        return [(row.date, float(row.vo2_max_precise)) for row in rows if row.vo2_max_precise]

    def _sleep_score_series(self, start: date, end: date) -> List[Tuple[date, float]]:
        from sqlalchemy import and_

        from ..database.models import Sleep

        rows = (
            self.db.query(Sleep.sleep_date, Sleep.overall_score, Sleep.sleep_score)
            .filter(and_(Sleep.sleep_date >= start, Sleep.sleep_date <= end))
            .order_by(Sleep.sleep_date)
            .all()
        )
        points: List[Tuple[date, float]] = []
        for row in rows:
            score = row.overall_score if row.overall_score is not None else row.sleep_score
            if score is not None:
                points.append((row.sleep_date, float(score)))
        return points

    def _durability_series(self, start: date, end: date) -> List[Tuple[date, float]]:
        coaching = CoachingDecisionMetricsService(self.db, self._ppap)
        points: List[Tuple[date, float]] = []
        current = start
        while current <= end:
            value = coaching.get_durability_score(current)
            if value is not None:
                points.append((current, float(value)))
            current += timedelta(days=7)
        return points

    def _activity_metric_series(
        self,
        start: date,
        end: date,
        column: str,
    ) -> List[Tuple[date, float]]:
        from sqlalchemy import and_, func

        from ..database.models.activity import Activity
        from ..utils.activity_filters import is_running_activity

        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .order_by(Activity.start_time)
            .all()
        )
        points: List[Tuple[date, float]] = []
        for activity in activities:
            if not is_running_activity(activity):
                continue
            value = getattr(activity, column, None)
            if value is None or activity.start_time is None:
                continue
            points.append((activity.start_time.date(), float(value)))
        return points

    def _lt_series(self, start: date, end: date, kind: str) -> List[Tuple[date, float]]:
        from sqlalchemy import func

        from ..database.models.lactate_threshold_history import LactateThresholdHistory

        rows = (
            self.db.query(LactateThresholdHistory)
            .filter(
                func.date(LactateThresholdHistory.observed_at) >= start,
                func.date(LactateThresholdHistory.observed_at) <= end,
            )
            .order_by(LactateThresholdHistory.observed_at)
            .all()
        )
        points: List[Tuple[date, float]] = []
        for row in rows:
            day = row.observed_at.date() if row.observed_at else None
            if day is None:
                continue
            if kind == "hr" and row.lactate_threshold_heart_rate:
                points.append((day, float(row.lactate_threshold_heart_rate)))
            elif kind == "pace" and row.lactate_threshold_speed and row.lactate_threshold_speed > 0:
                points.append((day, 1000.0 / float(row.lactate_threshold_speed)))
        return points

    def _compute_trend(
        self,
        metric: str,
        series: List[Tuple[date, float]],
        start: date,
        end: date,
        window_days: int,
    ) -> Dict[str, Any]:
        values = [v for _d, v in series]
        sample_count = len(values)

        empty: Dict[str, Any] = {
            "metric": metric,
            "current": None,
            "baseline": None,
            "absolute_change": None,
            "relative_change_pct": None,
            "slope": None,
            "direction": "uncertain",
            "sample_count": sample_count,
            "confidence": 0.0,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "change_point_detected": False,
        }

        if sample_count == 0:
            return empty

        current = values[-1]
        baseline_window = max(3, min(sample_count, window_days // 4 or 3))
        baseline_values = values[:baseline_window]
        baseline = sum(baseline_values) / len(baseline_values)

        absolute_change = current - baseline
        relative_change_pct = (
            (absolute_change / baseline) * 100.0 if baseline != 0 else None
        )

        slope = self._theil_sen_slope(series) if sample_count >= MIN_SAMPLES_FOR_SLOPE else None
        direction = self._direction(metric, relative_change_pct, slope, sample_count)
        change_point = self._detect_change_point(values)

        confidence = confidence_from_sample_count(sample_count)
        if sample_count < MIN_SAMPLES_FOR_DIRECTION:
            confidence *= 0.5
        if slope is None:
            confidence *= 0.85

        higher_is_better = metric not in {
            "resting_hr",
            "hr_drift",
            "decoupling",
            "lactate_threshold_pace",
        }

        return {
            "metric": metric,
            "current": round(current, 4),
            "baseline": round(baseline, 4),
            "absolute_change": round(absolute_change, 4),
            "relative_change_pct": round(relative_change_pct, 2) if relative_change_pct is not None else None,
            "slope": round(slope, 6) if slope is not None else None,
            "direction": direction,
            "sample_count": sample_count,
            "confidence": round(confidence, 2),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "change_point_detected": change_point,
            "higher_is_better": higher_is_better,
        }

    def _theil_sen_slope(self, series: List[Tuple[date, float]]) -> Optional[float]:
        if len(series) < MIN_SAMPLES_FOR_SLOPE:
            return None
        origin = series[0][0]
        xs = [(day - origin).days for day, _v in series]
        ys = [v for _d, v in series]
        slopes: List[float] = []
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                dx = xs[j] - xs[i]
                if dx == 0:
                    continue
                slopes.append((ys[j] - ys[i]) / dx)
        if not slopes:
            return None
        return median(slopes)

    def _direction(
        self,
        metric: str,
        relative_change_pct: Optional[float],
        slope: Optional[float],
        sample_count: int,
    ) -> TrendDirection:
        if sample_count < MIN_SAMPLES_FOR_DIRECTION:
            return "uncertain"
        if relative_change_pct is None and slope is None:
            return "uncertain"

        higher_is_better = metric not in {
            "resting_hr",
            "hr_drift",
            "decoupling",
            "lactate_threshold_pace",
        }

        rel = relative_change_pct or 0.0
        if abs(rel) < STABLE_RELATIVE_CHANGE_PCT and (slope is None or abs(slope) < 1e-6):
            return "stable"

        improving = rel > STABLE_RELATIVE_CHANGE_PCT
        if not higher_is_better:
            improving = rel < -STABLE_RELATIVE_CHANGE_PCT

        if slope is not None:
            slope_improving = slope > 0
            if not higher_is_better:
                slope_improving = slope < 0
            if abs(slope) > 1e-6:
                improving = slope_improving

        if abs(rel) < STABLE_RELATIVE_CHANGE_PCT * 2 and slope is None:
            return "stable"
        return "improving" if improving else "declining"

    def _detect_change_point(self, values: List[float]) -> bool:
        if len(values) < 8:
            return False
        mid = len(values) // 2
        early = values[:mid]
        late = values[mid:]
        if len(early) < 3 or len(late) < 3:
            return False
        early_mean = sum(early) / len(early)
        late_mean = sum(late) / len(late)
        early_std = self._pstdev(early)
        if early_std <= 0:
            return abs(late_mean - early_mean) > 0.01
        z = abs(late_mean - early_mean) / early_std
        return z >= CHANGE_POINT_Z_THRESHOLD

    @staticmethod
    def _pstdev(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean_val = sum(values) / len(values)
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)
        return math.sqrt(variance)
