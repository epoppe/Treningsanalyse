"""Treningsmonotoni, strain og hard-day densitet — supplement til CTL/ATL/TSB."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .metric_evidence import confidence_from_sample_count
from .coaching_session_types import HARD_SESSION_TYPES
from .coaching_constants import HARD_DAYS_7D_MAX, MONOTONY_HIGH, RAPID_LOAD_RATIO
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import SessionClassifierService
from .training_stress_service import TrainingStressService

HARD_DENSITY_7D_HIGH = HARD_DAYS_7D_MAX


class LoadVariabilityService:
    """Rapporterer load-variabilitet uten å gjøre ACWR til skadeprediktor."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._tss = TrainingStressService(db)
        self._classifier = SessionClassifierService(db, storage)

    def analyze(
        self,
        day: Optional[date] = None,
        *,
        window_days: int = 7,
    ) -> Dict[str, Any]:
        day = day or date.today()
        start = day - timedelta(days=window_days - 1)
        daily_loads = self._daily_loads(start, day)
        loads = list(daily_loads.values())

        monotony = None
        strain = None
        variability = None
        if len(loads) >= 3:
            avg = mean(loads)
            std = pstdev(loads) if len(loads) > 1 else 0.0
            variability = round(std, 2)
            if std > 0:
                monotony = round(avg / std, 2)
                strain = round(sum(loads) * monotony, 1)

        hard_7 = self._hard_day_count(day, 7)
        hard_14 = self._hard_day_count(day, 14)
        consecutive = self._max_consecutive_load_days(daily_loads)

        load_7 = sum(loads)
        prior_start = start - timedelta(days=window_days)
        prior_loads = self._daily_loads(prior_start, start - timedelta(days=1))
        prior_sum = sum(prior_loads.values())
        rapid_ratio = (load_7 / prior_sum) if prior_sum > 0 else None

        flags: List[str] = []
        if monotony is not None and monotony >= MONOTONY_HIGH:
            flags.append("monotonous_loading")
        if rapid_ratio is not None and rapid_ratio >= RAPID_LOAD_RATIO:
            flags.append("rapid_load_change")
        if hard_7 >= HARD_DENSITY_7D_HIGH:
            flags.append("high_hard_session_density")
        if consecutive >= 5:
            flags.append("consecutive_load_concentration")
        if hard_7 >= 2 and self._hard_day_count(day, 2) >= 2:
            flags.append("inadequate_recovery_spacing")

        confidence = confidence_from_sample_count(
            sum(1 for v in loads if v > 0),
            min_samples=3,
            target_samples=7,
        )

        return {
            "date": day.isoformat(),
            "window_days": window_days,
            "daily_load_variability": variability,
            "training_monotony": monotony,
            "training_strain": strain,
            "consecutive_load_days_max": consecutive,
            "hard_day_density_7d": hard_7,
            "hard_day_density_14d": hard_14,
            "rapid_load_ratio_vs_prior_window": round(rapid_ratio, 2) if rapid_ratio is not None else None,
            "flags": flags,
            "confidence": confidence,
            "context": {
                "ctl": self._ppap.get_ctl(day),
                "atl": self._ppap.get_atl(day),
                "tsb": self._ppap.get_tsb(day),
                "note": "ACWR/monotony are descriptive risk markers — not injury predictions.",
            },
        }

    def _daily_loads(self, start: date, end: date) -> Dict[date, float]:
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
        daily: Dict[date, float] = {}
        current = start
        while current <= end:
            daily[current] = 0.0
            current += timedelta(days=1)
        for activity in activities:
            if not activity.start_time:
                continue
            day = activity.start_time.date()
            if day not in daily:
                continue
            load = activity.training_stress_score or activity.epoc
            if load:
                daily[day] += float(load)
            else:
                try:
                    daily[day] += float(self._tss.calculate_tss_for_activity(activity) or 0.0)
                except Exception:
                    pass
        return daily

    def _hard_day_count(self, day: date, window: int) -> int:
        count = 0
        for offset in range(window):
            check = day - timedelta(days=offset)
            activities = (
                self.db.query(Activity)
                .options(joinedload(Activity.activity_type))
                .filter(func.date(Activity.start_time) == check)
                .all()
            )
            for activity in activities:
                if not is_running_activity(activity):
                    continue
                st = self._classifier.classify_activity(activity, end_date=check).get("session_type")
                if st in HARD_SESSION_TYPES:
                    count += 1
                    break
        return count

    @staticmethod
    def _max_consecutive_load_days(daily_loads: Dict[date, float]) -> int:
        best = 0
        run = 0
        for day in sorted(daily_loads):
            if daily_loads[day] > 0:
                run += 1
                best = max(best, run)
            else:
                run = 0
        return best
