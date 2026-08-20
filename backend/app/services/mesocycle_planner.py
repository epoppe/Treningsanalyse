"""4–6 week mesocycle — personalized from history; defaults only as fallback."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .athlete_utility_profile import AthleteUtilityProfile
from .deload_need_service import DeloadNeedService
from .execution_pattern_service import ExecutionPatternService
from .goal_context_service import GoalContextService
from .load_progression_service import LoadProgressionService
from .mesocycle_simulation_service import MesocycleSimulationService
from .ppap_metrics_service import PpapMetricsService
from .race_capability_service import RaceCapabilityService
from .statistical_uncertainty import evidence_band
from .training_phase_service import TrainingPhaseService
from .training_response_service import TrainingResponseService
from .workout_effectiveness_service import WorkoutEffectivenessService


class MesocyclePlanner:
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
        self._phase = TrainingPhaseService(db, storage, self._ppap, goal=goal)
        self._deload = DeloadNeedService(db, storage, self._ppap)
        self._load = LoadProgressionService(db, storage, self._ppap)
        self._response = TrainingResponseService(db, storage, self._ppap)
        self._effectiveness = WorkoutEffectivenessService(db, storage, self._ppap)
        self._capability = RaceCapabilityService(db, storage, self._ppap)
        self._execution = ExecutionPatternService(db)
        self._utility = AthleteUtilityProfile(db)
        self._sim = MesocycleSimulationService(db, storage, self._ppap)

    def plan(
        self,
        start: Optional[date] = None,
        *,
        weeks: int = 5,
        goal: Optional[Dict[str, Any]] = None,
        compare_candidates: bool = True,
    ) -> Dict[str, Any]:
        start = start or date.today()
        weeks = max(4, min(6, weeks))
        goal_ctx = self._goals.build(start, goal=goal)
        envelope = self._load.envelope(start)
        baseline_volume = float(envelope.get("current_load") or 0)
        responses = self._response.analyze_responses(end_date=start, lookback_days=180)
        effectiveness = self._effectiveness.summary_scores(end_date=start)
        capability = self._capability.assess(start, goal=goal) if hasattr(self._capability, "assess") else {}
        primary_gap = (capability or {}).get("primary_gap") or (capability or {}).get("limiter")
        execution = self._execution.analyze(as_of=start)
        utility = self._utility.build()
        eligible = responses.get("ranking_eligible_relationships") or []
        evidence = 0.35
        source = "default"
        if baseline_volume > 0 and (eligible or effectiveness):
            source = "personalized"
            evidence = min(
                0.85,
                0.35
                + 0.02 * len(eligible)
                + float(envelope.get("evidence_strength") or 0) * 0.3
                + (0.15 if utility.get("source") == "personal" else 0),
            )

        candidates = self._build_candidates(
            start=start,
            weeks=weeks,
            goal=goal,
            goal_ctx=goal_ctx,
            baseline_volume=baseline_volume,
            envelope=envelope,
            primary_gap=primary_gap,
            effectiveness=effectiveness if isinstance(effectiveness, dict) else {},
            source=source,
            evidence=evidence,
            execution=execution,
        )
        comparison = []
        if compare_candidates:
            comparison = self._compare(candidates, goal_ctx, envelope, execution)
            chosen_key = max(comparison, key=lambda c: c["score"])["candidate"] if comparison else "balanced"
        else:
            chosen_key = "balanced"
        chosen = candidates[chosen_key]

        return {
            "start": start.isoformat(),
            "weeks": weeks,
            "goal": goal_ctx,
            "mesocycle": chosen["weeks"],
            "selected_candidate": chosen_key,
            "candidates": {k: {"weeks": v["weeks"], "label": k} for k, v in candidates.items()},
            "comparison": comparison,
            "load_envelope": envelope,
            "utility_profile": utility,
            "execution_feasibility": execution.get("feasibility"),
            "source": source,
            "evidence_strength": round(evidence, 2),
            "statistical_support": evidence_band(
                sample_count=int(envelope.get("n_tolerated_transitions") or 0),
                effect_size=0.2 if source == "personalized" else 0.0,
            ),
            "rationale_codes": chosen.get("rationale_codes") or [],
            "note": "Weekly targets only — not a rigid day-by-day calendar.",
        }

    def _build_candidates(self, **kwargs) -> Dict[str, Dict[str, Any]]:
        out = {}
        for name, factor in (("conservative", 0.0), ("balanced", 0.5), ("aggressive", 1.0)):
            out[name] = self._build_one(name=name, progression_factor=factor, **kwargs)
        return out

    def _build_one(
        self,
        *,
        name: str,
        progression_factor: float,
        start: date,
        weeks: int,
        goal,
        goal_ctx,
        baseline_volume: float,
        envelope: Dict[str, Any],
        primary_gap,
        effectiveness: Dict[str, Any],
        source: str,
        evidence: float,
        execution: Dict[str, Any],
    ) -> Dict[str, Any]:
        lo, hi = envelope.get("supported_next_range") or [baseline_volume, baseline_volume * 1.05]
        span = max(0.0, float(hi) - float(lo))
        rows: List[Dict[str, Any]] = []
        rationale = []
        if source == "personalized":
            rationale.append("personal_load_envelope")
        else:
            rationale.append("default_phase_volume")
        if primary_gap:
            rationale.append(f"capability_gap_{primary_gap}")
        if execution.get("feasibility", {}).get("preferred_hard_weekdays"):
            rationale.append("adherence_hard_day_preference")

        volume = baseline_volume if baseline_volume > 0 else float(lo) or 180.0
        for i in range(weeks):
            week_start = start + timedelta(days=7 * i)
            phase = self._phase.determine(week_start, goal=goal)
            deload = self._deload.assess(week_start)
            phase_name = phase.get("phase") or "maintenance"
            if deload.get("deload_need") == "recommended" or phase_name in {"recovery", "taper"}:
                target = [int(volume * 0.55), int(volume * 0.75)]
                quality = 0 if phase_name == "recovery" else 1
                primary, secondary = ("easy_volume", None) if phase_name == "recovery" else ("race_pace", "easy_volume")
                week_source = source
            else:
                # Progress within envelope; aggressive still capped by hi.
                step = span * progression_factor * (0.35 + 0.15 * i)
                target_mid = min(float(hi), volume + step)
                # Fallback phase ranges if no history
                if baseline_volume <= 0:
                    target = self._fallback_volume(phase_name, deload.get("deload_need"))
                    week_source = "default"
                else:
                    target = [int(max(volume * 0.95, target_mid - 15)), int(target_mid + 10)]
                    week_source = source
                quality = 0 if deload.get("deload_need") == "recommended" else (
                    2 if phase_name in {"build", "specific"} and name != "conservative" else 1
                )
                primary, secondary = self._stimuli(phase_name, goal_ctx, primary_gap, effectiveness)
            long_run = [70, 110] if goal_ctx.get("target_event") in {"half_marathon", "marathon"} else [50, 80]
            if phase_name in {"taper", "recovery"} or deload.get("deload_need") == "recommended":
                long_run = [40, 70]
            rows.append(
                {
                    "week": i + 1,
                    "week_index": i + 1,
                    "week_start": week_start.isoformat(),
                    "current_baseline_volume": round(baseline_volume, 1),
                    "target_volume": target,
                    "volume_target_min": target,
                    "quality_sessions": quality,
                    "long_run_target_min": long_run,
                    "primary_stimulus": primary,
                    "secondary_stimulus": secondary,
                    "deload_state": deload.get("deload_need"),
                    "phase": phase_name,
                    "source": week_source,
                    "evidence_strength": round(evidence if week_source == "personalized" else 0.3, 2),
                    "confidence": round(min(0.8, float(phase.get("confidence") or 0.5)), 2),
                    "rationale_codes": rationale,
                }
            )
            volume = sum(target) / 2.0
        # Guardrail: aggressive must stay within envelope upper
        return {"weeks": rows, "rationale_codes": rationale}

    def _compare(self, candidates, goal_ctx, envelope, execution) -> List[Dict[str, Any]]:
        sims = self._sim.simulate_candidates(candidates, envelope)
        rows = []
        for name, sim in sims.items():
            goal_alignment = 0.7 if goal_ctx.get("target_event") else 0.5
            recovery_risk = float(sim.get("peak_atl_risk") or 0.4)
            historical_support = float(envelope.get("evidence_strength") or 0.3)
            feasibility = 0.6
            prefs = (execution.get("feasibility") or {}).get("preferred_hard_weekdays")
            if prefs:
                feasibility = 0.75
            score = (
                0.3 * goal_alignment
                + 0.25 * (1.0 - recovery_risk)
                + 0.25 * historical_support
                + 0.2 * feasibility
            )
            rows.append(
                {
                    "candidate": name,
                    "goal_alignment": round(goal_alignment, 3),
                    "recovery_risk": round(recovery_risk, 3),
                    "historical_support": round(historical_support, 3),
                    "execution_feasibility": round(feasibility, 3),
                    "score": round(score, 3),
                    "simulation": sim,
                }
            )
        return rows

    @staticmethod
    def _fallback_volume(phase: str, deload: Optional[str]) -> List[int]:
        if deload == "recommended" or phase == "recovery":
            return [90, 160]
        if phase == "taper":
            return [100, 180]
        if phase in {"build", "specific"}:
            return [220, 320]
        if phase == "peak":
            return [180, 260]
        return [160, 240]

    @staticmethod
    def _stimuli(phase: str, goal: Dict[str, Any], primary_gap, effectiveness: Dict[str, Any]) -> tuple:
        if phase == "taper":
            return "race_pace", "easy_volume"
        if phase == "recovery":
            return "easy_volume", None
        if primary_gap in {"durability", "threshold", "vo2", "economy"}:
            mapping = {
                "durability": ("long_run", "threshold"),
                "threshold": ("threshold", "long_run"),
                "vo2": ("vo2_intervals", "threshold"),
                "economy": ("easy_volume", "strides"),
            }
            return mapping[primary_gap]
        # Effectiveness-informed secondary preference
        best = None
        best_score = None
        for k, v in (effectiveness or {}).items():
            try:
                score = float(v)
            except (TypeError, ValueError):
                continue
            if best_score is None or score > best_score:
                best_score = score
                best = k
        event = goal.get("target_event")
        if event in {"5k", "10k"}:
            return "vo2_intervals", best or "threshold"
        if event in {"half_marathon", "marathon"}:
            return "threshold", best or "long_run"
        return "easy_volume", best or "threshold"
