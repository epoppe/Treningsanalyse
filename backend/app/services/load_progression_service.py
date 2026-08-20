"""Personal load progression envelope — not a 10% rule, not an injury limit."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .load_variability_service import LoadVariabilityService
from .ppap_metrics_service import PpapMetricsService
from .statistical_uncertainty import evidence_band


class LoadProgressionService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._variability = LoadVariabilityService(db, storage, self._ppap)

    def envelope(self, day: Optional[date] = None, *, lookback_weeks: int = 16) -> Dict[str, Any]:
        day = day or date.today()
        weeks = self._weekly_volumes(day, lookback_weeks)
        current = weeks[-1][1] if weeks else 0.0
        tolerated_bumps: List[float] = []
        for i in range(1, len(weeks)):
            prev, cur = weeks[i - 1][1], weeks[i][1]
            week_end = weeks[i][0]
            if prev <= 0:
                continue
            if not self._week_was_tolerable(week_end):
                continue
            bump = (cur - prev) / prev
            if -0.05 <= bump <= 0.25:
                tolerated_bumps.append(bump)

        if len(tolerated_bumps) >= 4:
            # Conservative upper: median of positive tolerated bumps
            positives = sorted(b for b in tolerated_bumps if b >= 0) or [0.0]
            mid = positives[len(positives) // 2]
            upper = current * (1.0 + mid)
            source = "historical_tolerance"
            evidence = min(0.85, 0.35 + 0.03 * len(tolerated_bumps))
            n = len(tolerated_bumps)
        else:
            # Conservative default envelope (~5%), not 10% rule as primary claim
            upper = current * 1.05 if current > 0 else 180.0
            source = "default_conservative"
            evidence = 0.3
            n = len(tolerated_bumps)

        lo = current
        hi = max(lo, upper)
        return {
            "current_load": round(current, 1),
            "supported_next_range": [round(lo, 1), round(hi, 1)],
            "upper_bound_source": source,
            "n_weeks": len(weeks),
            "n_tolerated_transitions": n,
            "evidence_strength": round(evidence, 2),
            "statistical_support": evidence_band(sample_count=n, effect_size=0.15 if n >= 4 else 0.0),
            "note": "Progression envelope from historical tolerance — not an injury threshold.",
        }

    def _weekly_volumes(self, day: date, lookback_weeks: int) -> List[Tuple[date, float]]:
        rows: List[Tuple[date, float]] = []
        for i in range(lookback_weeks, 0, -1):
            week_end = day - timedelta(days=7 * (i - 1))
            week_start = week_end - timedelta(days=6)
            minutes = self._minutes_between(week_start, week_end)
            rows.append((week_end, minutes))
        return rows

    def _minutes_between(self, start: date, end: date) -> float:
        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    Activity.start_time >= start.isoformat(),
                    Activity.start_time < (end + timedelta(days=1)).isoformat(),
                )
            )
            .all()
        )
        total = 0.0
        for act in activities:
            if not is_running_activity(act):
                continue
            if act.duration is not None:
                total += float(act.duration) / 60.0
        return total

    def _week_was_tolerable(self, week_end: date) -> bool:
        try:
            variability = self._variability.analyze(week_end)
        except Exception:
            variability = {}
        monotony = (variability or {}).get("monotony")
        if monotony is not None and float(monotony) > 2.2:
            return False
        hrv = self._ppap.get_hrv_delta_pct(week_end)
        # Missing HRV is not treated as negative.
        if hrv is not None and hrv < -15:
            return False
        rhr = self._ppap.get_rhr_delta_bpm(week_end)
        if rhr is not None and rhr > 6:
            return False
        tsb = self._ppap.get_tsb(week_end)
        if tsb is not None and tsb < -30:
            return False
        return True
