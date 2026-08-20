"""Analyserer historisk sammenheng mellom treningsbelastning og senere utfall — uten kausalitet."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .adaptive_threshold_service import AdaptiveThresholdService
from .coaching_analysis_service import CoachingAnalysisService
from .mcp_derived_metrics_service import McpDerivedMetricsService
from .ppap_metrics_service import PpapMetricsService

DEFAULT_LAG_WINDOWS = (7, 14, 21, 28)
STIMULUS_WINDOW_DAYS = 7

STIMULUS_METRICS = (
    "easy_volume",
    "threshold_volume",
    "high_intensity_volume",
    "weekly_tss",
)

OUTCOME_METRICS = {
    "easy_efficiency": "fitness.ef_30d",
    "critical_speed": "running.critical_speed",
    "threshold_pace": "__threshold_pace__",
    "vo2max": "__vo2max__",
    "hrv": "cardio.hrv_7d",
    "resting_hr": "cardio.rhr_7d",
    "durability": "__durability__",
}


class TrainingResponseService:
    """Konservativ analyse av load→response med LT1/LT2-soner og eksplisitte begrensninger."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._derived = McpDerivedMetricsService(db, storage)
        self._coaching = CoachingAnalysisService(db, storage)
        self._thresholds = AdaptiveThresholdService(db, storage)

    def analyze_responses(
        self,
        *,
        end_date: Optional[date] = None,
        lookback_days: int = 365,
        lag_windows: Tuple[int, ...] = DEFAULT_LAG_WINDOWS,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)
        relationships: List[Dict[str, Any]] = []

        for stimulus_key in STIMULUS_METRICS:
            for outcome_key in OUTCOME_METRICS:
                best = self._best_lag_relationship(
                    stimulus_key,
                    outcome_key,
                    start,
                    end,
                    lag_windows,
                )
                if best is not None:
                    relationships.append(best)

        return {
            "end_date": end.isoformat(),
            "lookback_days": lookback_days,
            "relationships": relationships,
            "disclaimer": "Correlations describe historical co-movement — not causal training effects.",
        }

    def analyze_dose_response(
        self,
        *,
        stimulus: str = "threshold_volume",
        outcome: str = "threshold_pace",
        end_date: Optional[date] = None,
        lookback_days: int = 365,
        lag_days: int = 21,
    ) -> Dict[str, Any]:
        """Observational dose buckets. Ikke kalt optimal dose."""
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)
        pairs: List[Tuple[float, float]] = []
        current = start + timedelta(days=lag_days + 7)
        while current <= end:
            stim = self._stimulus_value(stimulus, current - timedelta(days=lag_days), current)
            out = self._outcome_value(outcome, current)
            if stim is not None and out is not None:
                pairs.append((stim, out))
            current += timedelta(days=7)

        if len(pairs) < 6:
            return {
                "stimulus": stimulus,
                "response": outcome,
                "dose_response": [],
                "best_supported_historical_range": None,
                "confidence": 0.0,
                "sample_count": len(pairs),
                "disclaimer": "observational_association_not_causal_not_optimal",
            }

        xs = sorted(p[0] for p in pairs)
        t1 = xs[len(xs) // 3]
        t2 = xs[(2 * len(xs)) // 3]
        buckets = [
            {"range": [0, round(t1, 1)], "values": []},
            {"range": [round(t1, 1), round(t2, 1)], "values": []},
            {"range": [round(t2, 1), round(xs[-1], 1)], "values": []},
        ]
        # For pace, lower is better; for EF/VO2/CS higher is better.
        invert = outcome in {"threshold_pace"}
        for stim, out in pairs:
            if stim <= t1:
                buckets[0]["values"].append(out)
            elif stim <= t2:
                buckets[1]["values"].append(out)
            else:
                buckets[2]["values"].append(out)

        dose_response = []
        best_idx = None
        best_score = None
        for idx, bucket in enumerate(buckets):
            vals = bucket["values"]
            mean_v = sum(vals) / len(vals) if vals else None
            score = (-mean_v if invert else mean_v) if mean_v is not None else None
            dose_response.append(
                {
                    "range": bucket["range"],
                    "effect": round(mean_v, 3) if mean_v is not None else None,
                    "sample_count": len(vals),
                    "label": ("low", "moderate", "high")[idx],
                }
            )
            if score is not None and (best_score is None or score > best_score) and len(vals) >= 3:
                best_score = score
                best_idx = idx

        best_range = dose_response[best_idx]["range"] if best_idx is not None else None
        conf = min(0.75, 0.2 + 0.02 * len(pairs))
        if best_range is None:
            conf = min(conf, 0.3)
        return {
            "stimulus": stimulus,
            "response": outcome,
            "lag_days": lag_days,
            "dose_response": dose_response,
            "best_supported_historical_range": best_range,
            "confidence": round(conf, 2),
            "sample_count": len(pairs),
            "disclaimer": "observational_association_not_causal — not an optimal_range",
        }

    def _best_lag_relationship(
        self,
        stimulus: str,
        outcome: str,
        start: date,
        end: date,
        lag_windows: Tuple[int, ...],
    ) -> Optional[Dict[str, Any]]:
        best: Optional[Dict[str, Any]] = None
        for lag in lag_windows:
            result = self._correlate(stimulus, outcome, start, end, lag)
            if result is None:
                continue
            if best is None or result["confidence"] > best["confidence"]:
                best = result
        return best

    def _correlate(
        self,
        stimulus: str,
        outcome: str,
        start: date,
        end: date,
        lag_days: int,
    ) -> Optional[Dict[str, Any]]:
        pairs: List[Tuple[float, float]] = []
        current = start + timedelta(days=lag_days + 7)
        while current <= end:
            stimulus_val = self._stimulus_value(stimulus, current - timedelta(days=lag_days), current)
            outcome_val = self._outcome_value(outcome, current)
            if stimulus_val is not None and outcome_val is not None:
                pairs.append((stimulus_val, outcome_val))
            current += timedelta(days=7)

        if len(pairs) < 5:
            return None

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        r = _pearson(xs, ys)
        if r is None or math.isnan(r):
            return None

        effect_size = round(r, 3)
        if abs(r) < 0.15:
            relationship = "uncertain"
        elif r > 0:
            relationship = "positive"
        else:
            relationship = "negative"

        confidence = min(0.9, abs(r) * confidence_from_samples(len(pairs)))

        return {
            "stimulus": stimulus,
            "outcome": outcome,
            "lag_days": lag_days,
            "relationship": relationship,
            "effect_size": effect_size,
            "confidence": round(confidence, 2),
            "sample_count": len(pairs),
            "limitations": [
                "observational_correlation_not_causation",
                "confounding_by_other_training_not_controlled",
            ],
        }

    def _stimulus_value(self, stimulus: str, start: date, end: date) -> Optional[float]:
        if stimulus == "weekly_tss":
            return self._weekly_tss_sum(start, end)

        zone_key = {
            "easy_volume": "low",
            "threshold_volume": "threshold",
            "high_intensity_volume": "high",
        }.get(stimulus)
        if zone_key is None:
            return None

        lt1, lt2 = self._threshold_hr_bounds(end)
        if lt1 is None or lt2 is None:
            return self._fallback_stimulus_minutes(stimulus, start, end)

        zone_seconds = self._zone_seconds_in_window(start, end, lt1, lt2)
        seconds = zone_seconds.get(zone_key, 0.0)
        return round(seconds / 60.0, 1) if seconds > 0 else None

    def _threshold_hr_bounds(self, end: date) -> Tuple[Optional[float], Optional[float]]:
        adaptive = self._thresholds.estimate_lt1(end_date=end)
        history = self._coaching._latest_threshold_history(end)
        lt2 = history.lactate_threshold_heart_rate if history else None
        lt1 = adaptive.get("lt1_hr")
        return (float(lt1) if lt1 else None, float(lt2) if lt2 else None)

    def _zone_seconds_in_window(
        self,
        start: date,
        end: date,
        lt1: float,
        lt2: float,
    ) -> Dict[str, float]:
        totals = {"low": 0.0, "threshold": 0.0, "high": 0.0}
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity):
                continue
            buckets, _method = self._coaching.get_activity_intensity_buckets(activity, lt1, lt2)
            for key in totals:
                totals[key] += float(buckets.get(key, 0.0))
        return totals

    def _weekly_tss_sum(self, start: date, end: date) -> Optional[float]:
        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        total = 0.0
        for activity in activities:
            if not is_running_activity(activity):
                continue
            tss = activity.training_stress_score or activity.epoc
            if tss:
                total += float(tss)
        return round(total, 1) if total > 0 else None

    def _fallback_stimulus_minutes(self, stimulus: str, start: date, end: date) -> Optional[float]:
        """Fallback når LT1/LT2 mangler — bruk session classifier som grov proxy."""
        from .session_classifier_service import SessionClassifierService

        classifier = SessionClassifierService(self.db, self.storage, self._coaching)
        total_min = 0.0
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        proxy_map = {
            "easy_volume": {"recovery_run", "easy_aerobic", "long_aerobic"},
            "threshold_volume": {"steady", "tempo", "threshold"},
            "high_intensity_volume": {"vo2_intervals", "anaerobic", "race"},
        }
        allowed = proxy_map.get(stimulus, set())
        for activity in activities:
            if not is_running_activity(activity) or not activity.duration:
                continue
            classification = classifier.classify_activity(activity, end_date=end)
            if classification.get("session_type") in allowed:
                total_min += float(activity.duration) / 60.0
        return round(total_min, 1) if total_min > 0 else None

    def _outcome_value(self, outcome: str, day: date) -> Optional[float]:
        if outcome == "durability":
            from .coaching_decision_metrics_service import CoachingDecisionMetricsService

            return CoachingDecisionMetricsService(self.db, self._ppap).get_durability_score(day)
        if outcome == "vo2max":
            from ..database.models.activity import GarminPerformanceMetric

            row = (
                self.db.query(GarminPerformanceMetric.vo2_max_precise)
                .filter(func.date(GarminPerformanceMetric.date) <= day)
                .order_by(GarminPerformanceMetric.date.desc())
                .first()
            )
            return float(row[0]) if row and row[0] is not None else None
        if outcome == "threshold_pace":
            history = self._coaching._latest_threshold_history(day)
            if history and history.lactate_threshold_speed and history.lactate_threshold_speed > 0:
                return 1000.0 / float(history.lactate_threshold_speed)
            return None

        metric_key = OUTCOME_METRICS.get(outcome)
        if not metric_key or metric_key.startswith("__"):
            return None
        value = self._derived._daily_metric_value(metric_key, day)
        return float(value) if value is not None else None


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def confidence_from_samples(n: int) -> float:
    if n < 5:
        return 0.3
    if n < 10:
        return 0.5
    if n < 20:
        return 0.7
    return 0.85
