"""Plan robustness, replanning policy, and plan stability from observed history."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import TrainingPlanVersion
from .status_semantics import DriftStatus


class PlanRobustnessService:
    def score(self, sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
        sessions = sessions or []
        hard = [s for s in sessions if s.get("type") in {"threshold", "vo2_intervals", "race_pace"}]
        easy = [s for s in sessions if s.get("type") in {"easy_run", "recovery_run", "long_run"}]
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
            score -= 0.15
        return {
            "robustness_score": round(min(1.0, max(0.0, score)), 3),
            "scenarios": scenarios,
            "note": "Plans that collapse after one miss score lower — do not auto-reschedule every miss.",
        }

    @staticmethod
    def _after_remove(sessions: List[Dict[str, Any]], prefer: str) -> bool:
        hard = {"threshold", "vo2_intervals", "race_pace"}
        if prefer == "easy":
            remaining = [s for s in sessions if s.get("type") not in {"easy_run", "recovery_run"}]
            return any(s.get("type") in hard or s.get("type") == "long_run" for s in remaining) or len(remaining) >= 2
        remaining_hard = [s for s in sessions if s.get("type") in hard]
        return len(remaining_hard) != 1


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
        if hrv_delta is not None and hrv_delta < -12 and recent_plan_changes == 0:
            return {"action": "adjust_one_session", "reason": "strong_recovery_signal", "materiality": "medium"}
        if hrv_delta is not None and hrv_delta < -6:
            return {"action": "do_not_replan", "reason": "hrv_noise_hysteresis", "materiality": "low"}
        return {"action": "do_not_replan", "reason": "stable", "materiality": "none"}


class PlanStabilityService:
    """
    Classify plan churn from observed TrainingPlanVersion history.

    Statuses: stable | adaptive | overreactive | insufficient_data
    Never report stable merely because there are few data points.
    """

    MIN_HISTORY_POINTS = 3

    def classify(
        self,
        plan_change_count_14d: int,
        *,
        material_changes: int = 0,
        history_points: Optional[int] = None,
        median_days_between_replans: Optional[float] = None,
        reason_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        points = history_points if history_points is not None else plan_change_count_14d
        if points < self.MIN_HISTORY_POINTS:
            return {
                "status": DriftStatus.INSUFFICIENT_DATA.value,
                "plan_change_count_14d": plan_change_count_14d,
                "material_changes": material_changes,
                "history_points": points,
                "median_days_between_replans": median_days_between_replans,
                "reason_codes": reason_codes or [],
                "note": "Insufficient plan history — absence of churn is not evidence of stability.",
            }

        if plan_change_count_14d <= 2:
            status = "stable"
        elif plan_change_count_14d <= 5 and material_changes >= max(1, plan_change_count_14d // 2):
            status = "adaptive"
        else:
            status = "overreactive"

        return {
            "status": status,
            "plan_change_count_14d": plan_change_count_14d,
            "material_changes": material_changes,
            "history_points": points,
            "median_days_between_replans": median_days_between_replans,
            "reason_codes": reason_codes or [],
            "note": "Do not optimize solely for stability — meaningful evidence should still change plans.",
        }

    def from_history(
        self,
        db: Session,
        *,
        as_of: Optional[date] = None,
        window_days: int = 28,
    ) -> Dict[str, Any]:
        as_of = as_of or date.today()
        start = as_of - timedelta(days=window_days)
        versions = (
            db.query(TrainingPlanVersion)
            .filter(TrainingPlanVersion.created_at.isnot(None))
            .order_by(TrainingPlanVersion.created_at.asc())
            .all()
        )
        in_window: List[TrainingPlanVersion] = []
        for v in versions:
            created = v.created_at
            if created is None:
                continue
            created_day = created.date() if isinstance(created, datetime) else created
            if isinstance(created_day, date) and start <= created_day <= as_of:
                in_window.append(v)

        material = 0
        reason_codes: List[str] = []
        for v in in_window:
            changes = v.changes_json or []
            if changes:
                material += 1
            reasons = v.reason_json
            if isinstance(reasons, dict):
                code = reasons.get("code") or reasons.get("reason")
                if code:
                    reason_codes.append(str(code))
            elif isinstance(reasons, list):
                reason_codes.extend(str(r) for r in reasons)
            elif isinstance(reasons, str) and reasons:
                reason_codes.append(reasons)

        gaps: List[float] = []
        for a, b in zip(in_window, in_window[1:]):
            if a.created_at and b.created_at:
                gaps.append(abs((b.created_at - a.created_at).total_seconds()) / 86400.0)
        median_gap = sorted(gaps)[len(gaps) // 2] if gaps else None

        # Use total known versions as history depth (not only window)
        history_points = len(versions)
        window_changes = len(in_window)

        result = self.classify(
            window_changes,
            material_changes=material,
            history_points=history_points,
            median_days_between_replans=round(median_gap, 2) if median_gap is not None else None,
            reason_codes=list(dict.fromkeys(reason_codes)),
        )
        result["window_days"] = window_days
        result["versions_in_window"] = window_changes
        result["total_versions"] = history_points
        return result
