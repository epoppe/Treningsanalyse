"""Ranger kandidatøkter med eksplisitte komponenter — ingen opaque ML-score."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

CANDIDATES = (
    "rest",
    "recovery_run",
    "easy_run",
    "long_run",
    "threshold",
    "vo2_intervals",
    "race_pace",
)

# Transparent vekting. Summen er en rangeringsnøkkel, ikke en sannsynlighet.
WEIGHTS = {
    "benefit_score": 0.22,
    "goal_alignment": 0.22,
    "limiter_alignment": 0.18,
    "historical_response": 0.10,
    "recovery_cost": -0.16,
    "risk_penalty": -0.12,
}

HARD = {"threshold", "vo2_intervals", "race_pace"}
QUALITY = HARD | {"long_run"}


class WorkoutCandidateRanker:
    """Guardrails styrer eligibility; ranking velger blant eligible."""

    def rank(
        self,
        context: Dict[str, Any],
        *,
        historical_by_type: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        historical_by_type = historical_by_type or {}
        evidence_strength = float(context.get("evidence_strength") or 0.5)
        rows: List[Dict[str, Any]] = []
        for workout in CANDIDATES:
            row = self._score_one(workout, context, historical_by_type)
            rows.append(row)

        eligible = [r for r in rows if r["eligible"]]
        eligible.sort(key=lambda r: r["ranking_score"], reverse=True)
        close = False
        if len(eligible) >= 2 and abs(eligible[0]["ranking_score"] - eligible[1]["ranking_score"]) < 8:
            close = True

        rec_conf = evidence_strength
        if close:
            rec_conf *= 0.7
        if len(eligible) <= 1:
            rec_conf = min(rec_conf, 0.55)
        use_fallback = evidence_strength < 0.4

        return {
            "candidates": rows,
            "ranked_eligible": [r["workout_type"] for r in eligible],
            "selected": eligible[0]["workout_type"] if eligible and not use_fallback else None,
            "close_race": close,
            "evidence_strength": round(evidence_strength, 2),
            "recommendation_confidence": round(max(0.15, min(0.95, rec_conf)), 2),
            "use_rule_fallback": use_fallback,
            "ranking_note": "ranking_score is a documented weighted sum of explicit components — not an ML probability.",
        }

    def _score_one(
        self,
        workout: str,
        ctx: Dict[str, Any],
        historical: Dict[str, float],
    ) -> Dict[str, Any]:
        eligible, reason = self._eligible(workout, ctx)
        limiter = ctx.get("top_limiter")
        phase = (ctx.get("training_phase") or {}).get("phase") or ctx.get("training_block")
        gap = (ctx.get("race_capability") or {}).get("primary_gap")
        flags = ((ctx.get("load_variability") or {}).get("flags")) or []

        benefit = 40.0
        limiter_align = 40.0
        goal_align = 40.0
        recovery_cost = 30.0
        risk = 20.0

        if workout == "threshold":
            benefit = 80.0 if limiter in {"threshold", None} else 55.0
            limiter_align = 90.0 if limiter == "threshold" or gap == "threshold" else 50.0
            goal_align = 85.0 if gap in {"threshold", None} and phase in {"build", "specific", "peak"} else 45.0
            recovery_cost = 70.0
            risk = 55.0
        elif workout == "vo2_intervals":
            benefit = 75.0 if limiter == "vo2" or gap == "vo2" else 45.0
            limiter_align = 90.0 if limiter == "vo2" else 40.0
            goal_align = 80.0 if (ctx.get("goal") or {}).get("target_event") in {"5k", "10k"} else 40.0
            recovery_cost = 80.0
            risk = 60.0
        elif workout == "race_pace":
            benefit = 70.0 if phase in {"specific", "peak", "taper"} else 35.0
            limiter_align = 60.0
            goal_align = 90.0 if (ctx.get("goal") or {}).get("goal_type") == "race" else 30.0
            recovery_cost = 65.0
            risk = 50.0
        elif workout == "long_run":
            benefit = 75.0 if gap in {"durability", "race_specific_endurance", "aerobic_base"} else 50.0
            limiter_align = 80.0 if gap in {"durability", "race_specific_endurance"} else 45.0
            goal_align = 85.0 if (ctx.get("goal") or {}).get("target_event") in {"half_marathon", "marathon"} else 40.0
            recovery_cost = 55.0
            risk = 40.0
        elif workout == "easy_run":
            benefit = 70.0 if limiter in {"aerobic", "consistency"} or phase in {"base", "build"} else 55.0
            limiter_align = 75.0 if limiter in {"aerobic", "consistency"} else 50.0
            goal_align = 60.0
            recovery_cost = 20.0
            risk = 10.0
        elif workout == "recovery_run":
            benefit = 80.0 if phase == "recovery" else 35.0
            limiter_align = 80.0 if limiter in {"fatigue", "sleep"} else 30.0
            goal_align = 30.0
            recovery_cost = 10.0
            risk = 5.0
        elif workout == "rest":
            benefit = 90.0 if (ctx.get("readiness") or 100) < 35 else 20.0
            limiter_align = 70.0 if limiter in {"fatigue", "sleep"} else 20.0
            goal_align = 15.0
            recovery_cost = 0.0
            risk = 0.0

        if "high_hard_session_density" in flags or "inadequate_recovery_spacing" in flags:
            if workout in HARD:
                risk += 25.0
        if "rapid_load_change" in flags or "monotonous_loading" in flags:
            if workout in QUALITY:
                risk += 15.0
                recovery_cost += 10.0

        hist = historical.get(workout)
        hist_score = float(hist) if hist is not None else 50.0

        ranking = 50.0
        ranking += WEIGHTS["benefit_score"] * benefit
        ranking += WEIGHTS["goal_alignment"] * goal_align
        ranking += WEIGHTS["limiter_alignment"] * limiter_align
        ranking += WEIGHTS["historical_response"] * hist_score
        ranking += WEIGHTS["recovery_cost"] * recovery_cost
        ranking += WEIGHTS["risk_penalty"] * risk

        return {
            "workout_type": workout,
            "benefit_score": round(benefit, 1),
            "recovery_cost": round(recovery_cost, 1),
            "goal_alignment": round(goal_align, 1),
            "limiter_alignment": round(limiter_align, 1),
            "historical_response": round(hist_score, 1),
            "risk_penalty": round(risk, 1),
            "evidence_strength": round(float(ctx.get("evidence_strength") or 0.5), 2),
            "eligible": eligible,
            "ineligible_reason": reason,
            "ranking_score": round(ranking, 1),
        }

    @staticmethod
    def _eligible(workout: str, ctx: Dict[str, Any]) -> tuple:
        readiness = ctx.get("readiness")
        tsb = ctx.get("tsb")
        hard_blocked = bool(ctx.get("hard_blocked"))
        rest_required = bool(ctx.get("rest_required"))
        recovery_required = bool(ctx.get("recovery_required"))
        flags = ((ctx.get("load_variability") or {}).get("flags")) or []

        if rest_required:
            return (workout == "rest", None if workout == "rest" else "rest_required")
        if recovery_required and workout in QUALITY:
            return False, "recovery_required"
        if workout in QUALITY and hard_blocked:
            return False, "hard_session_guardrail"
        if workout in HARD and "high_hard_session_density" in flags:
            return False, "high_hard_session_density"
        if workout == "long_run" and (ctx.get("training_phase") or {}).get("phase") == "recovery":
            return False, "recovery_phase"
        if workout == "rest" and readiness is not None and readiness >= 55 and tsb is not None and tsb > -10:
            return False, "rest_not_indicated"
        return True, None
