"""Analyserer historisk sammenheng mellom treningsbelastning og senere utfall — uten kausalitet."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .mcp_derived_metrics_service import McpDerivedMetricsService
from .ppap_metrics_service import PpapMetricsService

DEFAULT_LAG_WINDOWS = (7, 14, 21, 28)

STIMULUS_METRICS = {
    "easy_volume": "easy_volume_minutes",
    "threshold_volume": "threshold_volume_minutes",
    "high_intensity_volume": "high_volume_minutes",
    "weekly_tss": "weekly_tss",
}

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
    """Konservativ analyse av load→response med eksplisitte begrensninger."""

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
        r = self._pearson(xs, ys)
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
            total = 0.0
            current = start
            while current <= end:
                ctl_series = self._ppap.get_ctl(current)
                if ctl_series is not None:
                    total += float(ctl_series)
                current += timedelta(days=1)
            return total / max(1, (end - start).days + 1)

        zone_key = {
            "easy_volume": "low",
            "threshold_volume": "threshold",
            "high_intensity_volume": "high",
        }.get(stimulus)
        if zone_key is None:
            return None

        total_minutes = 0.0
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
        for activity in activities:
            if not is_running_activity(activity) or not activity.duration:
                continue
            total_minutes += float(activity.duration) / 60.0
        return total_minutes if total_minutes > 0 else None

    def _outcome_value(self, outcome: str, day: date) -> Optional[float]:
        if outcome == "durability":
            from .coaching_decision_metrics_service import CoachingDecisionMetricsService

            return CoachingDecisionMetricsService(self.db, self._ppap).get_durability_score(day)
        metric_key = OUTCOME_METRICS.get(outcome)
        if not metric_key:
            return None
        if metric_key.startswith("__"):
            return None
        value = self._derived._daily_metric_value(metric_key, day)
        return float(value) if value is not None else None


def confidence_from_samples(n: int) -> float:
    if n < 5:
        return 0.3
    if n < 10:
        return 0.5
    if n < 20:
        return 0.7
    return 0.85
