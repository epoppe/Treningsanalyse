"""Eksplisitt målkontekst fra konfigurasjon — uten å anta at target_time er realistisk."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..storage import DataStorage
from .adaptive_threshold_service import AdaptiveThresholdService
from .ppap_metrics_service import PpapMetricsService

SUPPORTED_EVENTS = ("5k", "10k", "half_marathon", "marathon")
SUPPORTED_GOAL_TYPES = ("race", "general_fitness", "aerobic_base")
EVENT_DISTANCE_M = {
    "5k": 5000.0,
    "10k": 10000.0,
    "half_marathon": 21097.5,
    "marathon": 42195.0,
}
# Andel av LT2-fart som grov prediksjon når CS mangler (lav confidence).
LT2_SPEED_FACTOR = {
    "5k": 1.08,
    "10k": 1.02,
    "half_marathon": 0.94,
    "marathon": 0.86,
}
EVENT_CAPABILITIES = {
    "5k": ["vo2", "threshold", "aerobic_base"],
    "10k": ["threshold", "vo2", "aerobic_base"],
    "half_marathon": ["aerobic_base", "threshold", "durability", "race_specific_endurance"],
    "marathon": ["aerobic_base", "durability", "race_specific_endurance", "threshold"],
}


class GoalContextService:
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
        self._thresholds = AdaptiveThresholdService(db, storage)
        self._goal_override = goal

    def build(
        self,
        day: Optional[date] = None,
        *,
        goal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        day = day or date.today()
        configured = goal or self._goal_override or self._from_settings()
        if not configured:
            return self._no_goal(day)

        goal_type = (configured.get("goal_type") or "race").lower()
        event = self._normalize_event(configured.get("event") or configured.get("target_event"))
        target_date = self._parse_date(configured.get("target_date"))
        target_time = configured.get("target_time_sec")
        priority = configured.get("priority") or "A"

        days_to_goal = (target_date - day).days if target_date else None
        predicted, pred_source, pred_conf = self._predicted_time(event, day)
        gap = None
        if predicted is not None and target_time is not None:
            gap = float(target_time) - float(predicted)

        feasibility = self._feasibility(target_time, predicted, pred_conf)
        target_pace = None
        if target_time and event in EVENT_DISTANCE_M:
            target_pace = round(float(target_time) / (EVENT_DISTANCE_M[event] / 1000.0), 1)

        required = EVENT_CAPABILITIES.get(event or "", ["aerobic_base"])
        return {
            "goal_type": goal_type if goal_type in SUPPORTED_GOAL_TYPES else "general_fitness",
            "target_event": event,
            "event": event,
            "target_date": target_date.isoformat() if target_date else None,
            "target_time_sec": int(target_time) if target_time else None,
            "target_pace_sec_km": target_pace,
            "priority": priority,
            "days_to_goal": days_to_goal,
            "current_predicted_performance": predicted,
            "prediction_source": pred_source,
            "performance_gap_sec": round(gap, 1) if gap is not None else None,
            "required_capabilities": required,
            "goal_feasibility": feasibility,
            "confidence": round(min(0.9, pred_conf * (0.8 if target_date else 0.5)), 2),
        }

    def _no_goal(self, day: date) -> Dict[str, Any]:
        return {
            "goal_type": "general_fitness",
            "target_event": None,
            "event": None,
            "target_date": None,
            "target_time_sec": None,
            "target_pace_sec_km": None,
            "priority": None,
            "days_to_goal": None,
            "current_predicted_performance": None,
            "prediction_source": None,
            "performance_gap_sec": None,
            "required_capabilities": ["aerobic_base", "consistency"],
            "goal_feasibility": {"status": "insufficient_data", "confidence": 0.0, "reason": "no_goal_configured"},
            "confidence": 0.2,
            "as_of": day.isoformat(),
        }

    def _from_settings(self) -> Optional[Dict[str, Any]]:
        settings = get_settings()
        if not settings.ATHLETE_GOAL_TYPE and not settings.ATHLETE_GOAL_EVENT:
            return None
        return {
            "goal_type": settings.ATHLETE_GOAL_TYPE or "race",
            "event": settings.ATHLETE_GOAL_EVENT,
            "target_date": settings.ATHLETE_GOAL_TARGET_DATE,
            "target_time_sec": settings.ATHLETE_GOAL_TARGET_TIME_SEC,
            "priority": settings.ATHLETE_GOAL_PRIORITY,
        }

    def _predicted_time(self, event: Optional[str], day: date) -> tuple:
        if event not in EVENT_DISTANCE_M:
            return None, None, 0.0
        cs, d_prime = self._ppap.get_critical_speed_snapshot(day)
        distance = EVENT_DISTANCE_M[event]
        if cs and float(cs) > 0:
            offset = float(d_prime or 0.0)
            time_s = (distance - offset) / float(cs)
            if time_s > 0:
                return round(time_s, 1), "critical_speed", 0.65
        lt2 = self._thresholds.latest_lt2(day)
        speed = lt2.get("lt2_speed_mps")
        if speed and float(speed) > 0:
            factor = LT2_SPEED_FACTOR[event]
            time_s = distance / (float(speed) * factor)
            conf = 0.25 if lt2.get("stale") else 0.4
            return round(time_s, 1), "lt2_speed_heuristic", conf
        return None, None, 0.0

    @staticmethod
    def _feasibility(
        target_time: Optional[float],
        predicted: Optional[float],
        pred_conf: float,
    ) -> Dict[str, Any]:
        if target_time is None:
            return {"status": "insufficient_data", "confidence": 0.2, "reason": "no_target_time"}
        if predicted is None or predicted <= 0:
            return {"status": "insufficient_data", "confidence": 0.15, "reason": "no_predicted_performance"}
        ratio = float(target_time) / float(predicted)
        if ratio >= 0.98:
            status = "realistic"
        elif ratio >= 0.93:
            status = "stretch"
        else:
            status = "unlikely"
        return {
            "status": status,
            "confidence": round(pred_conf, 2),
            "target_vs_predicted_ratio": round(ratio, 3),
            "note": "Feasibility is observational vs current prediction — not a race guarantee.",
        }

    @staticmethod
    def _normalize_event(event: Optional[str]) -> Optional[str]:
        if not event:
            return None
        mapping = {
            "hm": "half_marathon",
            "half": "half_marathon",
            "half-marathon": "half_marathon",
            "m": "marathon",
            "5k": "5k",
            "10k": "10k",
            "marathon": "marathon",
            "half_marathon": "half_marathon",
        }
        return mapping.get(str(event).lower().strip())

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
