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
from .statistical_uncertainty import block_bootstrap_delta
from .temporal_metric_contract import (
    contract_for_trend,
    effective_sample_count,
    personal_noise_threshold,
)

TrendDirection = str  # improving|stable|declining|uncertain

TREND_WINDOWS_DAYS = (7, 28, 90, 365)

# Estimator constraints for Theil-Sen / direction, not evidence-policy floors.
MIN_SAMPLES_FOR_SLOPE = 5
MIN_SAMPLES_FOR_DIRECTION = 3
CHANGE_POINT_Z_THRESHOLD = 2.0

METRIC_FETCHERS: Dict[str, str] = {
    "vo2max": "__custom_vo2max__",
    "lactate_threshold_hr": "__custom_lt_hr__",
    "lactate_threshold_pace": "__custom_lt_pace__",
    "easy_run_efficiency": "fitness.ef_30d",
    "hr_drift": "cardio.drift_score",
    "decoupling": "cardio.drift_score",
    "critical_speed": "running.critical_speed",
    "ctl": "fitness.ctl",
    "atl": "fitness.atl",
    "consistency": "consistency.score",
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

    def series_for_metric(
        self,
        metric: str,
        *,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """HTTP-facing series points — same fetch path as analyze_metric (no new math)."""
        points = self._fetch_series(metric, start_date, end_date)
        return [{"date": day.isoformat(), "value": round(value, 4)} for day, value in points]

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

    def summarize_period(
        self,
        metric: str,
        *,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Metric-specific level over an exact [start, end] window."""
        series = self._fetch_series(metric, start_date, end_date)
        values = [value for _day, value in series]
        contract = contract_for_trend(metric)
        method = contract.period_summary if contract else "latest_snapshot"
        span_days = max(1, (end_date - start_date).days + 1)
        smoothing = contract.smoothing_window_days if contract else None
        raw_n = len(values)
        effective_n = effective_sample_count(
            raw_n,
            span_days=span_days,
            smoothing_window_days=smoothing,
        )
        coverage = round(raw_n / span_days, 3) if span_days else 0.0
        summary: Dict[str, Any] = {
            "metric": metric,
            "method": method,
            "unit": contract.display_unit if contract else None,
            "temporal_semantics": contract.temporal_semantics if contract else None,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "period_days": span_days,
            "value": None,
            "end_value": round(values[-1], 4) if values else None,
            "mean": round(sum(values) / len(values), 4) if values else None,
            "median": round(median(values), 4) if values else None,
            "best": None,
            "sample_count": raw_n,
            "raw_sample_count": raw_n,
            "effective_sample_count": effective_n,
            "coverage_ratio": coverage,
            "smoothing_window_days": smoothing,
            "point_in_time": method in {"latest_snapshot", "end_and_mean"},
        }
        if not values:
            return summary
        rule = contract.direction if contract else "higher_is_better"
        if rule == "lower_is_better":
            best = min(values)
        elif rule == "higher_is_better":
            best = max(values)
        else:
            best = None
        summary["best"] = round(best, 4) if best is not None else None
        if method == "median":
            level = summary["median"]
        elif method == "mean":
            level = summary["mean"]
        elif method == "sum":
            level = round(sum(values), 4)
        elif method == "best":
            level = summary["best"]
        elif method == "end_and_mean":
            level = summary["end_value"]
        else:
            level = summary["end_value"]
        summary["value"] = level
        return summary

    def compare_periods(
        self,
        metric: str,
        *,
        start_a: date,
        end_a: date,
        start_b: date,
        end_b: date,
    ) -> Dict[str, Any]:
        period_a = self.summarize_period(metric, start_date=start_a, end_date=end_a)
        period_b = self.summarize_period(metric, start_date=start_b, end_date=end_b)
        a_val = period_a.get("value")
        b_val = period_b.get("value")
        absolute = None
        relative = None
        if isinstance(a_val, (int, float)) and isinstance(b_val, (int, float)):
            absolute = round(float(a_val) - float(b_val), 4)
            if b_val == 0:
                relative = None
            else:
                relative = round((float(a_val) - float(b_val)) / abs(float(b_val)) * 100.0, 2)
        series_a = [v for _d, v in self._fetch_series(metric, start_a, end_a)]
        series_b = [v for _d, v in self._fetch_series(metric, start_b, end_b)]
        uncertainty = block_bootstrap_delta(series_a, series_b)
        contract = contract_for_trend(metric)
        noise = personal_noise_threshold(
            self._fetch_series(metric, start_b, end_a),
            contract,
            baseline=b_val if isinstance(b_val, (int, float)) else None,
        )
        effect = None
        if absolute is not None and noise["threshold_absolute"] > 0:
            effect = round(abs(absolute) / noise["threshold_absolute"], 2)
        ci = uncertainty.get("ci95")
        crosses_zero = bool(ci and ci[0] <= 0 <= ci[1])
        effective_n = min(
            int(period_a.get("effective_sample_count") or 0),
            int(period_b.get("effective_sample_count") or 0),
        )
        if absolute is None or effective_n < 3 or crosses_zero:
            status = "uncertain"
        elif effect is not None and effect < 1.0:
            status = "stable_within_noise"
        else:
            status = self._direction(
                metric,
                float(absolute),
                noise["threshold_absolute"],
                effective_n,
                max(int(period_a.get("raw_sample_count") or period_a.get("sample_count") or 0), MIN_SAMPLES_FOR_DIRECTION),
            )
        return {
            "metric": metric,
            "unit": period_a.get("unit"),
            "period_a_summary": period_a,
            "period_b_summary": period_b,
            "absolute_delta": absolute,
            "relative_delta": relative,
            "effect_vs_personal_noise": effect,
            "sample_count": min(int(period_a["sample_count"]), int(period_b["sample_count"])),
            "effective_sample_count": effective_n,
            "coverage": {
                "period_a": period_a.get("coverage_ratio"),
                "period_b": period_b.get("coverage_ratio"),
            },
            "uncertainty": uncertainty,
            "evidence": status,
            "from_zero": bool(b_val == 0 and a_val not in (None, 0)),
        }

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

        contract = contract_for_trend(metric)
        smoothing = contract.smoothing_window_days if contract else None
        span_days = max(1, (end - start).days + 1)
        effective_n = effective_sample_count(
            sample_count,
            span_days=span_days,
            smoothing_window_days=smoothing,
        )
        empty: Dict[str, Any] = {
            "metric": metric,
            "current": None,
            "baseline": None,
            "absolute_change": None,
            "relative_change_pct": None,
            "slope": None,
            "slope_per_day": None,
            "slope_per_week": None,
            "slope_per_28d": None,
            "standardized_slope": None,
            "direction": "uncertain",
            "sample_count": sample_count,
            "raw_sample_count": sample_count,
            "observation_days": sample_count,
            "coverage_ratio": round(sample_count / span_days, 3),
            "smoothing_window_days": smoothing,
            "effective_sample_count": effective_n,
            "temporal_semantics": contract.temporal_semantics if contract else None,
            "native_cadence_days": contract.native_cadence_days if contract else None,
            "unit": contract.display_unit if contract else None,
            "confidence": 0.0,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "window_days": window_days,
            "change_point_detected": False,
            "change_point": {
                "change_detected": False,
                "change_date": None,
            },
            "meaningful_change": None,
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
        noise = personal_noise_threshold(series, contract, baseline=baseline)
        direction = self._direction(
            metric,
            absolute_change,
            noise["threshold_absolute"],
            effective_n,
            sample_count,
        )
        change_point = self._detect_change_point(series)

        confidence = confidence_from_sample_count(effective_n)
        if sample_count < MIN_SAMPLES_FOR_DIRECTION:
            confidence *= 0.5
        if slope is None:
            confidence *= 0.85

        rule = contract.direction if contract else "higher_is_better"
        if rule == "context":
            higher_is_better = None
        else:
            higher_is_better = rule != "lower_is_better"
        slope_per_week = slope * 7.0 if slope is not None else None
        standardized = None
        if slope_per_week is not None and noise["threshold_absolute"] > 0:
            standardized = slope_per_week / noise["threshold_absolute"]

        return {
            "metric": metric,
            "current": round(current, 4),
            "baseline": round(baseline, 4),
            "absolute_change": round(absolute_change, 4),
            "relative_change_pct": round(relative_change_pct, 2) if relative_change_pct is not None else None,
            "slope": round(slope, 6) if slope is not None else None,
            "slope_per_day": round(slope, 6) if slope is not None else None,
            "slope_per_week": round(slope_per_week, 6) if slope_per_week is not None else None,
            "slope_per_28d": round(slope * 28.0, 6) if slope is not None else None,
            "standardized_slope": round(standardized, 3) if standardized is not None else None,
            "direction": direction,
            "sample_count": sample_count,
            "raw_sample_count": sample_count,
            "observation_days": sample_count,
            "coverage_ratio": round(sample_count / span_days, 3),
            "smoothing_window_days": smoothing,
            "effective_sample_count": effective_n,
            "temporal_semantics": contract.temporal_semantics if contract else None,
            "native_cadence_days": contract.native_cadence_days if contract else None,
            "unit": contract.display_unit if contract else None,
            "confidence": round(confidence, 2),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "window_days": window_days,
            "change_point_detected": bool(change_point.get("change_detected")),
            "change_point": change_point,
            "meaningful_change": noise,
            "higher_is_better": higher_is_better,
            "direction_rule": rule,
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
        absolute_change: float,
        noise_threshold: float,
        effective_n: int,
        sample_count: int,
    ) -> TrendDirection:
        if sample_count < MIN_SAMPLES_FOR_DIRECTION or effective_n < 2:
            return "uncertain"
        if abs(absolute_change) < max(noise_threshold, 0.0):
            return "stable_within_noise"
        contract = contract_for_trend(metric)
        rule = contract.direction if contract else "higher_is_better"
        if rule == "context":
            return "higher" if absolute_change > 0 else "lower"
        higher_is_better = rule != "lower_is_better"
        improving = absolute_change > 0 if higher_is_better else absolute_change < 0
        return "improving" if improving else "declining"

    def _detect_change_point(self, series: List[Any]) -> Dict[str, Any]:
        """Scan split points. Returns the strongest robust shift and its date."""
        if series and isinstance(series[0], tuple):
            dates = [item[0] for item in series]
            values = [float(item[1]) for item in series]
        else:
            dates = [None] * len(series)
            values = [float(item) for item in series]
        empty = {
            "change_detected": False,
            "change_date": None,
            "before_level": None,
            "after_level": None,
            "absolute_shift": None,
            "standardized_shift": None,
            "evidence": "insufficient",
        }
        n = len(values)
        if n < 8:
            return empty
        min_segment = max(4, n // 5)
        best: Optional[Dict[str, Any]] = None
        for split in range(min_segment, n - min_segment + 1):
            before = values[:split]
            after = values[split:]
            before_level = float(median(before))
            after_level = float(median(after))
            scale = self._pooled_mad(before, after)
            shift = after_level - before_level
            impurity = self._mean_abs_dev(before, before_level) + self._mean_abs_dev(after, after_level)
            if scale <= 1e-9:
                standardized = 0.0 if abs(shift) < 1e-6 else 99.0
            else:
                standardized = abs(shift) / scale
            if standardized < CHANGE_POINT_Z_THRESHOLD:
                continue
            candidate = {
                "change_detected": True,
                "change_date": dates[split].isoformat() if hasattr(dates[split], "isoformat") else None,
                "before_level": round(before_level, 4),
                "after_level": round(after_level, 4),
                "absolute_shift": round(shift, 4),
                "standardized_shift": round(float(standardized), 3),
                "evidence": "moderate" if standardized < 4 else "supported",
                "split_index": split,
                "_impurity": impurity,
            }
            rank = (float(candidate["standardized_shift"]), -impurity)
            if best is None or rank > best["_rank"]:
                candidate["_rank"] = rank
                best = candidate
        if best is None:
            return empty
        best.pop("_rank", None)
        best.pop("_impurity", None)
        return best

    @staticmethod
    def _pooled_mad(before: List[float], after: List[float]) -> float:
        def _mad(vals: List[float]) -> float:
            if not vals:
                return 0.0
            mid = float(median(vals))
            return float(median([abs(v - mid) for v in vals]))

        left = _mad(before)
        right = _mad(after)
        # 1.4826 * MAD is a robust scale. Used only as a heuristic effect denominator.
        return 1.4826 * ((left + right) / 2.0)

    @staticmethod
    def _mean_abs_dev(values: List[float], level: float) -> float:
        if not values:
            return 0.0
        return sum(abs(value - level) for value in values) / len(values)

    @staticmethod
    def _pstdev(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean_val = sum(values) / len(values)
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)
        return math.sqrt(variance)
