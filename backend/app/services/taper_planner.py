"""Race-specific taper with personal history when enough races exist."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .goal_context_service import GoalContextService
from .ppap_metrics_service import PpapMetricsService
from .statistical_uncertainty import evidence_band

DEFAULTS = {
    "5k": {"duration_days": 7, "volume_reduction_range": [0.35, 0.50], "intensity_maintenance": True},
    "10k": {"duration_days": 10, "volume_reduction_range": [0.30, 0.45], "intensity_maintenance": True},
    "half_marathon": {"duration_days": 14, "volume_reduction_range": [0.35, 0.55], "intensity_maintenance": True},
    "marathon": {"duration_days": 21, "volume_reduction_range": [0.40, 0.60], "intensity_maintenance": True},
}

MIN_RACES_FOR_PERSONAL = 4


class TaperPlanner:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
        goal: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._goals = GoalContextService(db, storage, self._ppap, goal=goal)

    def plan(self, day: Optional[date] = None, *, goal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        day = day or date.today()
        goal_ctx = self._goals.build(day, goal=goal)
        event = goal_ctx.get("target_event") or "half_marathon"
        base = dict(DEFAULTS.get(event, DEFAULTS["half_marathon"]))
        personal = self._personal_taper(day, event)
        if personal and personal.get("sample_count", 0) >= MIN_RACES_FOR_PERSONAL:
            return {
                "event": event,
                "race_date": goal_ctx.get("target_date"),
                "duration_days": personal["duration_days"],
                "volume_reduction_range": personal["volume_reduction_range"],
                "intensity_maintenance": base["intensity_maintenance"],
                "source": "personal_history",
                "sample_count": personal["sample_count"],
                "evidence_strength": personal["evidence_strength"],
                "statistical_support": evidence_band(
                    sample_count=personal["sample_count"],
                    effect_size=0.2,
                ),
                "current_fatigue_tsb": self._ppap.get_tsb(day),
                "note": "Personal taper from race history — observational, not causal.",
            }

        # Default / mild fatigue adjustment (not claimed as personal_history)
        tsb = self._ppap.get_tsb(day)
        ctl = self._ppap.get_ctl(day)
        source = "default"
        evidence = 0.35
        if tsb is not None and tsb < -15:
            base["duration_days"] = int(base["duration_days"] + 3)
            lo, hi = base["volume_reduction_range"]
            base["volume_reduction_range"] = [min(0.7, lo + 0.05), min(0.75, hi + 0.05)]
            source = "default_fatigue_adjusted"
            evidence = 0.4
        if ctl is not None and ctl > 80 and event in {"half_marathon", "marathon"}:
            base["duration_days"] = max(base["duration_days"], 14 if event == "half_marathon" else 21)
            source = "default_fatigue_adjusted"
            evidence = max(evidence, 0.42)
        return {
            "event": event,
            "race_date": goal_ctx.get("target_date"),
            "duration_days": base["duration_days"],
            "volume_reduction_range": base["volume_reduction_range"],
            "intensity_maintenance": base["intensity_maintenance"],
            "source": source,
            "sample_count": (personal or {}).get("sample_count") or 0,
            "evidence_strength": evidence,
            "statistical_support": evidence_band(sample_count=0, effect_size=0.0),
            "current_fatigue_tsb": tsb,
            "note": "Low race sample → defaults. Personal taper requires ≥4 races.",
        }

    def _personal_taper(self, day: date, event: str) -> Optional[Dict[str, Any]]:
        races = self._find_races(day)
        if len(races) < 1:
            return {"sample_count": 0}
        durations = []
        reductions = []
        for race_day, race_load in races:
            pre_start = race_day - timedelta(days=28)
            taper_start_candidates = []
            # Find when load dropped ≥25% vs prior 2-week mean
            baseline = self._mean_weekly_load(pre_start, race_day - timedelta(days=14))
            if baseline <= 0:
                continue
            for d in range(5, 25):
                window_start = race_day - timedelta(days=d)
                taper_load = self._mean_weekly_load(window_start, race_day - timedelta(days=1))
                if taper_load <= baseline * 0.75:
                    taper_start_candidates.append(d)
                    reductions.append(1.0 - (taper_load / baseline))
                    break
            if taper_start_candidates:
                durations.append(taper_start_candidates[-1])
        n = len(durations)
        if n < MIN_RACES_FOR_PERSONAL:
            return {"sample_count": n}
        durations.sort()
        reductions.sort()
        dur = durations[len(durations) // 2]
        lo = reductions[max(0, len(reductions) // 4)]
        hi = reductions[min(len(reductions) - 1, (3 * len(reductions)) // 4)]
        return {
            "duration_days": int(dur),
            "volume_reduction_range": [round(max(0.15, lo), 2), round(min(0.7, hi), 2)],
            "sample_count": n,
            "evidence_strength": round(min(0.8, 0.35 + 0.05 * n), 2),
        }

    def _find_races(self, day: date) -> List[Tuple[date, float]]:
        activities = (
            self.db.query(Activity)
            .filter(Activity.start_time < day.isoformat())
            .order_by(Activity.start_time.desc())
            .limit(400)
            .all()
        )
        races = []
        for act in activities:
            if not is_running_activity(act):
                continue
            name = (act.activity_name or "").lower()
            dist = float(act.distance or 0)
            # Heuristic race detection: named race or typical race distances
            is_race = "race" in name or "løp" in name or "marathon" in name or "half" in name
            if not is_race and dist > 0:
                # Approximate race distances in meters
                is_race = any(abs(dist - target) / target < 0.05 for target in (5000, 10000, 21097, 42195))
            if not is_race:
                continue
            act_day = act.start_time.date() if hasattr(act.start_time, "date") else date.fromisoformat(str(act.start_time)[:10])
            races.append((act_day, float(act.duration or 0)))
            if len(races) >= 12:
                break
        return races

    def _mean_weekly_load(self, start: date, end: date) -> float:
        if end <= start:
            return 0.0
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
        total_min = 0.0
        for act in activities:
            if is_running_activity(act) and act.duration:
                total_min += float(act.duration) / 60.0
        weeks = max(1.0, (end - start).days / 7.0)
        return total_min / weeks
