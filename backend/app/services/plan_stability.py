"""Plan robustness, replanning policy, and plan stability metrics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class PlanRobustnessService:
    def score(self, sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
        sessions = sessions or []
        hard = [s for s in sessions if s.get("type") in {"threshold", "vo2_intervals", "race_pace"}]
        easy = [s for s in sessions if s.get("type") in {"easy_run", "recovery_run", "long_run"}]
        # Simulate disruptions
        scenarios = {
            "missed_easy": self._after_remove(sessions, prefer="easy"),
            "missed_quality": self._after_remove(sessions, prefer="hard"),
            "long_run_shifted": len([s for s in sessions if s.get("type") == "long_run"]) > 0,
            "fatigue_day": len(hard) <= 1,
        }
        score = 0.7
        if len(easy) >= 3:
            score += 0.1
        if len(hard) <= 2:
            score += 0.1
        if scenarios["fatigue_day"]:
            score += 0.05
        if not scenarios["missed_quality"]:
            score -= 0.15  # plan had no quality buffer / single quality collapses week intent
        return {
            "robustness_score": round(min(1.0, max(0.0, score)), 3),
            "scenarios": scenarios,
            "note": "Plans that collapse after one miss score lower — do not auto-reschedule every miss.",
        }

    @staticmethod
    def _after_remove(sessions: List[Dict[str, Any]], prefer: str) -> bool:
        """Return True if week still has a coherent aerobic core after one removal."""
        hard = {"threshold", "vo2_intervals", "race_pace"}
        if prefer == "easy":
            remaining = [s for s in sessions if s.get("type") not in {"easy_run", "recovery_run"}]
            # still ok if long/quality remain
            return any(s.get("type") in hard or s.get("type") == "long_run" for s in remaining) or len(remaining) >= 2
        # missed quality
        remaining_hard = [s for s in sessions if s.get("type") in hard]
        return len(remaining_hard) != 1  # single quality → fragile if that one is missed


class ReplanningPolicy:
    """Explicit when-not-to / when-to replan with hysteresis against HRV noise."""

    def decide(
        self,
        *,
        hrv_delta: Optional[float] = None,
        pain: Optional[int] = None,
        unavailable: bool = False,
        missed_quality: bool = False,
        missed_easy: bool = False,
        material_goal_change: bool = False,
        recent_plan_changes: int = 0,
    ) -> Dict[str, Any]:
        if unavailable or (pain is not None and pain >= 3):
            return {
                "action": "adjust_one_session",
                "reason": "safety_or_availability",
                "materiality": "high",
            }
        if material_goal_change:
            return {"action": "rebuild_mesocycle", "reason": "goal_change", "materiality": "high"}
        if missed_quality and recent_plan_changes < 2:
            return {"action": "adjust_one_session", "reason": "missed_quality", "materiality": "medium"}
        if missed_easy:
            return {"action": "do_not_replan", "reason": "missed_easy_tolerate", "materiality": "low"}
        # Daily HRV noise — hysteresis: only act on strong signal and low recent churn
        if hrv_delta is not None and hrv_delta < -12 and recent_plan_changes == 0:
            return {"action": "adjust_one_session", "reason": "strong_recovery_signal", "materiality": "medium"}
        if hrv_delta is not None and hrv_delta < -6:
            return {"action": "do_not_replan", "reason": "hrv_noise_hysteresis", "materiality": "low"}
        return {"action": "do_not_replan", "reason": "stable", "materiality": "none"}


class PlanStabilityService:
    def classify(self, plan_change_count_14d: int, *, material_changes: int = 0) -> Dict[str, Any]:
        if plan_change_count_14d <= 2:
            status = "stable"
        elif plan_change_count_14d <= 5 and material_changes >= plan_change_count_14d // 2:
            status = "adaptive"
        else:
            status = "overreactive"
        return {
            "status": status,
            "plan_change_count_14d": plan_change_count_14d,
            "material_changes": material_changes,
            "note": "Do not optimize solely for stability — meaningful evidence should still change plans.",
        }
