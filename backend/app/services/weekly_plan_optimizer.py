"""Feasible ukeplaner mot availability — eksplisitte scores, ikke opaque optimizer."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .next_best_workout_service import NextBestWorkoutService
from .plan_simulation_service import PlanSimulationService
from .ppap_metrics_service import PpapMetricsService
from .training_availability_service import TrainingAvailabilityService
from .workout_prescription_service import WorkoutPrescriptionService
from .execution_pattern_service import ExecutionPatternService

HARD = {"threshold", "vo2_intervals", "race_pace"}
CROSS = {"strength", "cycling", "swimming", "tennis", "other"}
PHASE_HARD_BUDGET = {
    "recovery": 0,
    "base": 1,
    "build": 1,
    "specific": 2,
    "peak": 1,
    "taper": 1,
    "maintenance": 1,
}


class WeeklyPlanOptimizer:
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
        self._next = NextBestWorkoutService(db, storage, self._ppap, goal=goal)
        self._avail = TrainingAvailabilityService(db)
        self._sim = PlanSimulationService(db, storage, self._ppap)
        self._rx = WorkoutPrescriptionService(db, storage, self._ppap)
        self._execution_patterns = ExecutionPatternService(db)

    def optimize(
        self,
        day: Optional[date] = None,
        *,
        goal: Optional[Dict[str, Any]] = None,
        include_treadmill: bool = False,
        next_rec: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        day = day or date.today()
        next_rec = next_rec or self._next.recommend(day, include_treadmill=include_treadmill, goal=goal)
        phase = (next_rec.get("training_phase") or {}).get("phase") or "maintenance"
        constraints = self._avail.constraints_for_week(day)
        spacing = self._spacing_days(next_rec)
        hard_budget = PHASE_HARD_BUDGET.get(phase, 1)
        event = (next_rec.get("goal") or {}).get("target_event")
        want_long = event in {"half_marathon", "marathon"} and phase not in {"recovery", "taper"}
        first = next_rec.get("workout_type") or "easy_run"

        candidates = [
            self._build_schedule(day, next_rec, constraints, phase, first, hard_budget, spacing, want_long, "next_first"),
            self._build_schedule(day, next_rec, constraints, phase, first, hard_budget, spacing, want_long, "weekend_long"),
            self._build_schedule(day, next_rec, constraints, phase, first, hard_budget, spacing, want_long, "easy_biased"),
        ]
        scored = []
        patterns = self._execution_patterns.analyze(as_of=day)
        preferred_hard = set((patterns.get("feasibility") or {}).get("preferred_hard_weekdays") or [])
        for schedule in candidates:
            sim = self._sim.simulate(schedule["sessions"], origin=day)
            scores = self._score(
                schedule, sim, constraints, phase, want_long, next_rec, preferred_hard=preferred_hard
            )
            schedule["simulation"] = sim
            schedule["scores"] = scores
            schedule["total_score"] = round(sum(scores.values()), 1)
            scored.append(schedule)
        scored.sort(key=lambda s: s["total_score"], reverse=True)
        chosen = scored[0]
        return {
            "week_start": day.isoformat(),
            "week_objective": chosen["week_objective"],
            "sessions": chosen["sessions"],
            "target_volume_min": chosen["target_volume_min"],
            "hard_sessions": sum(1 for s in chosen["sessions"] if s.get("type") in HARD),
            "confidence": round(min(0.85, float(next_rec.get("recommendation_confidence") or 0.5)), 2),
            "adaptation_rules": [
                "Respect availability and date overrides",
                "If HRV drops beyond calibrated warning, delay quality 24–48h",
                "Projected future readiness is not observed",
                "Prefer historically adhered hard-session weekdays when evidence exists",
            ],
            "phase": phase,
            "availability_constraints": constraints,
            "selected_strategy": chosen["strategy"],
            "scores": chosen["scores"],
            "simulation": chosen["simulation"],
            "execution_feasibility": patterns.get("feasibility"),
            "alternatives": [
                {
                    "strategy": s["strategy"],
                    "sessions": [{"day_offset": x["day_offset"], "type": x["type"]} for x in s["sessions"]],
                    "scores": s["scores"],
                    "total_score": s["total_score"],
                }
                for s in scored[1:]
            ],
            "recommended_next_session": {
                "workout_type": first,
                "prescription": next_rec.get("workout_prescription"),
            },
            "projected_week": chosen["simulation"],
        }

    def _build_schedule(
        self,
        day: date,
        next_rec: Dict[str, Any],
        constraints: List[Dict[str, Any]],
        phase: str,
        first: str,
        hard_budget: int,
        spacing: int,
        want_long: bool,
        strategy: str,
    ) -> Dict[str, Any]:
        sessions: List[Dict[str, Any]] = []
        hard_placed = 0
        last_hard = -99
        first_capped = self._fit(first, constraints[0], next_rec.get("workout_prescription"), phase, day)
        sessions.append(first_capped)
        if first_capped["type"] in HARD:
            hard_placed += 1
            last_hard = 0

        long_slots = [i for i, c in enumerate(constraints) if c.get("allows_long_run") and c.get("available")]
        if not long_slots:
            long_slots = [i for i, c in enumerate(constraints) if i >= 5 and c.get("available")]
        long_offset = None
        if want_long and long_slots:
            long_offset = long_slots[-1] if strategy == "weekend_long" else long_slots[0]
            if long_offset == 0 and first != "long_run":
                long_offset = long_slots[-1] if len(long_slots) > 1 else None

        for offset in range(1, 7):
            constraint = constraints[offset]
            if not constraint.get("available"):
                sessions.append(self._session(offset, "rest", None, [0, 0], reason=constraint.get("reason") or "unavailable"))
                continue
            if long_offset == offset:
                sessions.append(self._fit("long_run", constraint, self._rx.prescribe("long_run", day=day, phase=phase), phase, day, offset))
                continue
            preferred = [str(p).lower() for p in (constraint.get("preferred_session_types") or [])]
            cross = next((p for p in preferred if p in CROSS), None)
            if cross and strategy != "weekend_long":
                sessions.append(self._session(offset, cross, None, [30, min(60, constraint.get("max_duration_min") or 60)]))
                continue
            place_hard = (
                hard_placed < hard_budget
                and strategy != "easy_biased"
                and (offset - last_hard) >= spacing
                and not constraint.get("avoid_hard")
                and phase != "recovery"
            )
            if place_hard:
                wtype = "race_pace" if phase == "taper" else "threshold"
                preferred = constraint.get("preferred_session_types") or []
                if preferred:
                    for cand in preferred:
                        if cand in HARD:
                            wtype = cand
                            break
                sessions.append(self._fit(wtype, constraint, self._rx.prescribe(wtype, day=day, phase=phase), phase, day, offset))
                hard_placed += 1
                last_hard = offset
                continue
            wtype = "recovery_run" if phase == "recovery" else "easy_run"
            sessions.append(self._fit(wtype, constraint, self._rx.prescribe(wtype, day=day, phase=phase), phase, day, offset))

        lo, hi = (90, 160) if phase == "recovery" else ((120, 200) if phase == "taper" else (180, 280))
        if phase in {"build", "specific"}:
            hi = 300
        objective = {
            "recovery": "restore and easy circulation only",
            "base": "aerobic volume within availability",
            "build": "aerobic volume + spaced quality",
            "specific": "race-specific work that fits the calendar",
            "peak": "sharpen without stacking hard days",
            "taper": "reduce load, keep race-pace reminders",
            "maintenance": "keep aerobic volume + one quality session",
        }.get(phase, "aerobic volume + one quality session")
        return {
            "strategy": strategy,
            "sessions": sessions,
            "week_objective": objective,
            "target_volume_min": [lo, hi],
        }

    def _fit(
        self,
        wtype: str,
        constraint: Dict[str, Any],
        prescription: Optional[Dict[str, Any]],
        phase: str,
        day: date,
        offset: int = 0,
    ) -> Dict[str, Any]:
        if not constraint.get("available"):
            return self._session(offset, "rest", None, [0, 0], reason=constraint.get("reason"))
        if wtype in HARD and constraint.get("avoid_hard"):
            wtype = "easy_run"
            prescription = self._rx.prescribe("easy_run", day=day, phase=phase)
        max_min = constraint.get("max_duration_min")
        duration = [30, 60]
        if prescription and prescription.get("total_duration_min"):
            total = int(prescription["total_duration_min"])
            duration = [max(20, total - 10), total + 5]
        if max_min is not None:
            duration = [min(d, int(max_min)) for d in duration]
            if duration[1] < 20 and wtype != "rest":
                wtype = "rest"
                prescription = None
                duration = [0, 0]
        return self._session(offset, wtype, prescription, duration)

    def _score(
        self,
        schedule: Dict[str, Any],
        sim: Dict[str, Any],
        constraints: List[Dict[str, Any]],
        phase: str,
        want_long: bool,
        next_rec: Dict[str, Any],
        preferred_hard: Optional[set] = None,
    ) -> Dict[str, float]:
        sessions = schedule["sessions"]
        types = [s.get("type") for s in sessions]
        goal_alignment = 70.0
        if (next_rec.get("race_capability") or {}).get("primary_gap") == "durability" and "long_run" in types:
            goal_alignment += 15
        if phase in {"build", "specific"} and any(t in HARD for t in types):
            goal_alignment += 10
        recovery_spacing = 80.0 if sim.get("hard_spacing_ok") else 30.0
        volume = 60.0
        total = sum(self._dur(s) for s in sessions)
        lo, hi = schedule["target_volume_min"]
        if lo <= total <= hi:
            volume = 85.0
        elif total < lo:
            volume = 50.0
        specificity = 50.0
        if want_long and "long_run" in types:
            specificity += 20
            long = next(s for s in sessions if s["type"] == "long_run")
            if constraints[int(long["day_offset"])].get("allows_long_run"):
                specificity += 15
        schedule_fit = 90.0
        for session, constraint in zip(sessions, constraints):
            if not constraint.get("available") and session.get("type") != "rest":
                schedule_fit -= 40
            max_min = constraint.get("max_duration_min")
            if max_min and self._dur(session) > max_min + 1:
                schedule_fit -= 20
            if constraint.get("avoid_hard") and session.get("type") in HARD:
                schedule_fit -= 25
        monotony_penalty = -20.0 if "monotonous_loading" in (sim.get("risk_flags") or []) else 0.0
        execution_feasibility = 50.0
        preferred_hard = preferred_hard or set()
        if preferred_hard:
            hard_offsets = [int(s["day_offset"]) for s in sessions if s.get("type") in HARD]
            # day_offset 0 = Monday-aligned week start weekday of origin; use offset as proxy
            hits = sum(1 for off in hard_offsets if off in preferred_hard or ((off % 7) in preferred_hard))
            execution_feasibility = 50.0 + 20.0 * hits
        return {
            "goal_alignment": round(goal_alignment, 1),
            "recovery_spacing": round(recovery_spacing, 1),
            "volume_alignment": round(volume, 1),
            "specificity": round(specificity, 1),
            "schedule_fit": round(max(0.0, schedule_fit), 1),
            "execution_feasibility": round(execution_feasibility, 1),
            "monotony_penalty": monotony_penalty,
        }

    @staticmethod
    def _dur(session: Dict[str, Any]) -> float:
        duration = session.get("duration_min")
        if isinstance(duration, (list, tuple)) and duration:
            return float(duration[-1])
        if isinstance(duration, (int, float)):
            return float(duration)
        return 0.0

    @staticmethod
    def _spacing_days(next_rec: Dict[str, Any]) -> int:
        for item in next_rec.get("decision_trace") or []:
            if item.get("factor") == "hard_session_spacing" and item.get("threshold"):
                return max(1, int(round(float(item["threshold"]) / 24.0)))
        return 2

    @staticmethod
    def _session(offset: int, wtype: str, prescription: Any, duration: Any, reason: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "day_offset": offset,
            "type": wtype,
            "duration_min": duration,
            "prescription": prescription,
        }
        if reason:
            payload["reason"] = reason
        return payload
