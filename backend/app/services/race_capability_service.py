"""Løpsspesifikke kapasiteter mot et mål — ikke bare VO2max/race predictor."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .adaptive_threshold_service import AdaptiveThresholdService
from .athlete_state_service import AthleteStateService
from .coaching_decision_metrics_service import CoachingDecisionMetricsService
from .goal_context_service import EVENT_CAPABILITIES, GoalContextService
from .ppap_metrics_service import PpapMetricsService


class RaceCapabilityService:
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
        self._state = AthleteStateService(db, storage, self._ppap)
        self._decision = CoachingDecisionMetricsService(self.db, self._ppap)
        self._goals = GoalContextService(db, storage, self._ppap, goal=goal)
        self._thresholds = AdaptiveThresholdService(db, storage)

    def assess(
        self,
        day: Optional[date] = None,
        *,
        goal: Optional[Dict[str, Any]] = None,
        event: Optional[str] = None,
    ) -> Dict[str, Any]:
        day = day or date.today()
        goal_ctx = self._goals.build(day, goal=goal)
        event = event or goal_ctx.get("target_event") or "half_marathon"
        state = self._state.build_state(day)
        lt2 = self._thresholds.latest_lt2(day)
        cs, _ = self._ppap.get_critical_speed_snapshot(day)
        durability = self._score((state.get("durability") or {}).get("value"), 100.0)
        aerobic = self._score((state.get("fitness") or {}).get("value"), 70.0)
        consistency = self._score((state.get("consistency") or {}).get("value"), 100.0)
        efficiency = self._score((state.get("aerobic_efficiency") or {}).get("value"), 0.03, scale=3000)
        threshold = 70.0 if lt2.get("lt2_hr") and not lt2.get("stale") else 40.0
        if lt2.get("stale"):
            threshold = 35.0
        cs_score = 70.0 if cs else 30.0
        long_run = durability

        capabilities = {
            "aerobic_base": self._cap(aerobic, efficiency, (state.get("fitness") or {}).get("confidence", 0.3)),
            "threshold": self._cap(threshold, None, float(lt2.get("confidence") or 0.3), evidence=["lt2_history"]),
            "critical_speed": self._cap(cs_score, None, 0.6 if cs else 0.2, evidence=["running.critical_speed"]),
            "durability": self._cap(durability, None, (state.get("durability") or {}).get("confidence", 0.3)),
            "race_specific_endurance": self._cap(long_run, consistency, 0.5, evidence=["long_run_quality", "consistency"]),
            "volume_consistency": self._cap(consistency, None, (state.get("consistency") or {}).get("confidence", 0.3)),
            "vo2": self._cap(cs_score, threshold, 0.45, evidence=["critical_speed", "lt2"]),
        }

        required = EVENT_CAPABILITIES.get(event, list(capabilities))
        gaps = {key: capabilities[key] for key in required if key in capabilities}
        primary_gap = min(gaps, key=lambda k: (gaps[k].get("value") or 0)) if gaps else None

        return {
            "event": event,
            "capabilities": capabilities,
            "primary_gap": primary_gap,
            "required_capabilities": required,
            "days_to_goal": goal_ctx.get("days_to_goal"),
            "note": "Capability scores are transparent heuristics from existing metrics — not lab tests.",
        }

    @staticmethod
    def _score(value: Any, typical: float, scale: Optional[float] = None) -> Optional[float]:
        if value is None:
            return None
        if scale:
            return max(0.0, min(100.0, float(value) * scale))
        return max(0.0, min(100.0, float(value) / typical * 70.0 + 15.0))

    @staticmethod
    def _cap(
        primary: Optional[float],
        secondary: Optional[float],
        confidence: Any,
        evidence: Optional[list] = None,
    ) -> Dict[str, Any]:
        if primary is None and secondary is None:
            value = None
            conf = 0.15
        elif secondary is None:
            value = primary
            conf = float(confidence or 0.3)
        elif primary is None:
            value = secondary
            conf = float(confidence or 0.3) * 0.8
        else:
            value = primary * 0.7 + secondary * 0.3
            conf = float(confidence or 0.3)
        return {
            "value": round(value, 1) if value is not None else None,
            "confidence": round(min(1.0, float(conf)), 2),
            "evidence": evidence or [],
        }
