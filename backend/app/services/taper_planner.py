"""Race-specific taper sketch with personal/default evidence."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .goal_context_service import GoalContextService
from .ppap_metrics_service import PpapMetricsService
from .statistical_uncertainty import evidence_band

DEFAULTS = {
    "5k": {"duration_days": 7, "volume_reduction_range": [0.35, 0.50], "intensity_maintenance": True},
    "10k": {"duration_days": 10, "volume_reduction_range": [0.30, 0.45], "intensity_maintenance": True},
    "half_marathon": {"duration_days": 14, "volume_reduction_range": [0.35, 0.55], "intensity_maintenance": True},
    "marathon": {"duration_days": 21, "volume_reduction_range": [0.40, 0.60], "intensity_maintenance": True},
}


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
        tsb = self._ppap.get_tsb(day)
        ctl = self._ppap.get_ctl(day)
        source = "default"
        evidence = 0.35
        # Mild personalization: high fatigue → slightly longer taper / more reduction
        if tsb is not None and tsb < -15:
            base["duration_days"] = int(base["duration_days"] + 3)
            lo, hi = base["volume_reduction_range"]
            base["volume_reduction_range"] = [min(0.7, lo + 0.05), min(0.75, hi + 0.05)]
            source = "personal"
            evidence = 0.45
        if ctl is not None and ctl > 80 and event in {"half_marathon", "marathon"}:
            base["duration_days"] = max(base["duration_days"], 14 if event == "half_marathon" else 21)
            source = "personal"
            evidence = max(evidence, 0.5)
        band = evidence_band(sample_count=8 if source == "personal" else 0, effect_size=0.2)
        return {
            "event": event,
            "race_date": goal_ctx.get("target_date"),
            "duration_days": base["duration_days"],
            "volume_reduction_range": base["volume_reduction_range"],
            "intensity_maintenance": base["intensity_maintenance"],
            "source": source,
            "evidence_strength": evidence,
            "statistical_support": band,
            "current_fatigue_tsb": tsb,
            "note": "Taper sketch — not a locked day-by-day prescription.",
        }
