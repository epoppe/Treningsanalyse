"""Treningsfase fra mål + tilstand — ikke kalender alene."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .athlete_state_service import AthleteStateService
from .coaching_decision_metrics_service import CoachingDecisionMetricsService
from .goal_context_service import GoalContextService
from .ppap_metrics_service import PpapMetricsService

PHASES = ("recovery", "base", "build", "specific", "peak", "taper", "maintenance")

BLOCK_TO_PHASE = {
    "recovery": "recovery",
    "overload": "recovery",
    "base": "base",
    "build": "build",
    "peak": "peak",
    "maintain": "maintenance",
}

OBJECTIVES = {
    "recovery": (["restore HRV/RHR", "easy aerobic only"], ["sleep"]),
    "base": (["increase aerobic volume", "improve durability"], ["maintain LT2"]),
    "build": (["increase aerobic volume", "develop LT2", "maintain VO2"], ["strides"]),
    "specific": (["race-specific endurance", "LT2 density", "long-run quality"], ["maintain VO2"]),
    "peak": (["sharpen race pace", "reduce residual fatigue"], ["keep aerobic volume"]),
    "taper": (["absorb load", "short race-pace reminders"], ["protect freshness"]),
    "maintenance": (["keep aerobic volume", "one quality session"], ["avoid monotony"]),
}


class TrainingPhaseService:
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
        self._decision = CoachingDecisionMetricsService(self.db, self._ppap)
        self._state = AthleteStateService(db, storage, self._ppap)
        self._goals = GoalContextService(db, storage, self._ppap, goal=goal)

    def determine(
        self,
        day: Optional[date] = None,
        *,
        goal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        day = day or date.today()
        goal_ctx = self._goals.build(day, goal=goal)
        block = self._decision.get_training_block(day)
        state = self._state.build_state(day)
        recovery = (state.get("recovery") or {}).get("value")
        durability = (state.get("durability") or {}).get("value")
        consistency = (state.get("consistency") or {}).get("value")
        ctl = (state.get("fitness") or {}).get("value")
        tsb = (state.get("load_tolerance") or {}).get("value")

        days = goal_ctx.get("days_to_goal")
        event = goal_ctx.get("target_event")
        reasons: List[str] = []

        phase = "maintenance"
        confidence = 0.45

        if recovery is not None and float(recovery) < 40:
            phase = "recovery"
            reasons.append("recovery_value_low")
            confidence = 0.8
        elif tsb is not None and float(tsb) < -22:
            phase = "recovery"
            reasons.append("tsb_very_low")
            confidence = 0.75
        elif event and days is not None:
            calendar_phase = self._calendar_phase(days)
            phase = calendar_phase
            reasons.append(f"days_to_event={days}")
            confidence = 0.7
            # Tilstandsjustering: kalender alene er ikke nok.
            if calendar_phase in {"build", "specific", "peak"} and (
                (consistency is not None and float(consistency) < 50)
                or (ctl is not None and float(ctl) < 25)
            ):
                phase = "base"
                reasons.append("fitness_or_consistency_insufficient_for_build")
                confidence = 0.65
            if calendar_phase in {"specific", "peak"} and event in {"half_marathon", "marathon"}:
                if durability is not None and float(durability) < 50:
                    phase = "specific"
                    reasons.append("durability_gap_keeps_specific")
            if calendar_phase == "taper" and tsb is not None and float(tsb) < -8:
                phase = "peak"
                reasons.append("still_fatigued_delay_taper")
        elif block:
            phase = BLOCK_TO_PHASE.get(block, "maintenance")
            reasons.append(f"training_block={block}")
            confidence = 0.55
        else:
            reasons.append("no_goal_no_block_default_maintenance")

        primary, secondary = OBJECTIVES.get(phase, ([], []))
        return {
            "phase": phase,
            "confidence": round(confidence, 2),
            "days_to_event": days,
            "primary_objectives": primary,
            "secondary_objectives": secondary,
            "training_block": block,
            "goal_type": goal_ctx.get("goal_type"),
            "reasons": reasons,
            "backwards_compatible_block": block,
        }

    @staticmethod
    def _calendar_phase(days: int) -> str:
        if days < 0:
            return "maintenance"
        if days <= 10:
            return "taper"
        if days <= 21:
            return "peak"
        if days <= 42:
            return "specific"
        if days <= 84:
            return "build"
        return "base"
