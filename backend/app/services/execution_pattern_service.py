"""Execution / adherence patterns from RecommendationExecution — feasibility evidence."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import RecommendationExecution, RecommendationRecord
from .statistical_uncertainty import evidence_band


class ExecutionPatternService:
    HARD = {"threshold", "vo2_intervals", "race_pace"}

    def __init__(self, db: Session):
        self.db = db

    def analyze(self, *, lookback_days: int = 365, as_of: Optional[date] = None) -> Dict[str, Any]:
        as_of = as_of or date.today()
        rows = (
            self.db.query(RecommendationExecution, RecommendationRecord, Activity)
            .outerjoin(RecommendationRecord, RecommendationExecution.recommendation_id == RecommendationRecord.id)
            .outerjoin(Activity, RecommendationExecution.activity_id == Activity.activity_id)
            .all()
        )
        patterns: List[Dict[str, Any]] = []

        hard_by_weekday: Dict[int, List[bool]] = defaultdict(list)
        long_shortened = []
        morning_quality = []
        modified = []

        for exec_row, rec, activity in rows:
            planned = exec_row.planned_type or (rec.recommended_workout_type if rec else None)
            status = exec_row.execution_status
            if activity is not None and activity.start_time is not None:
                weekday = activity.start_time.weekday()
                if planned in self.HARD:
                    hard_by_weekday[weekday].append(status in {"completed", "modified", "partial"})
                hour = activity.start_time.hour if isinstance(activity.start_time, datetime) else None
                if hour is not None and hour < 10 and exec_row.overall_adherence is not None:
                    morning_quality.append(float(exec_row.overall_adherence))
            if planned == "long_run" and exec_row.planned_duration and exec_row.actual_duration:
                if float(exec_row.actual_duration) < 0.85 * float(exec_row.planned_duration):
                    long_shortened.append(True)
                else:
                    long_shortened.append(False)
            if status == "modified":
                modified.append(planned or "unknown")

        for weekday, outcomes in hard_by_weekday.items():
            if not outcomes:
                continue
            rate = sum(1 for o in outcomes if o) / len(outcomes)
            patterns.append(
                {
                    "pattern": f"hard_session_weekday_{weekday}",
                    "execution_probability": round(rate, 3),
                    "sample_count": len(outcomes),
                    "confidence": round(min(0.85, 0.2 + 0.03 * len(outcomes)), 2),
                    "statistical_support": evidence_band(sample_count=len(outcomes), effect_size=rate - 0.5),
                }
            )

        if long_shortened:
            rate = sum(1 for x in long_shortened if x) / len(long_shortened)
            patterns.append(
                {
                    "pattern": "long_run_shortened",
                    "execution_probability": round(1.0 - rate, 3),
                    "sample_count": len(long_shortened),
                    "confidence": round(min(0.8, 0.2 + 0.03 * len(long_shortened)), 2),
                    "statistical_support": evidence_band(sample_count=len(long_shortened), effect_size=abs(rate - 0.5)),
                }
            )

        if morning_quality:
            mean_q = sum(morning_quality) / len(morning_quality)
            patterns.append(
                {
                    "pattern": "morning_session_adherence",
                    "execution_probability": round(mean_q, 3),
                    "sample_count": len(morning_quality),
                    "confidence": round(min(0.8, 0.2 + 0.03 * len(morning_quality)), 2),
                    "statistical_support": evidence_band(sample_count=len(morning_quality), effect_size=abs(mean_q - 0.5)),
                }
            )

        if modified:
            from collections import Counter

            common = Counter(modified).most_common(3)
            for planned_type, count in common:
                patterns.append(
                    {
                        "pattern": f"prescription_often_modified_{planned_type}",
                        "execution_probability": round(count / max(1, len(rows)), 3),
                        "sample_count": count,
                        "confidence": round(min(0.75, 0.15 + 0.04 * count), 2),
                        "statistical_support": evidence_band(sample_count=count, effect_size=0.2),
                    }
                )

        # Feasibility summary for WeeklyPlanOptimizer
        hard_probs = [p for p in patterns if p["pattern"].startswith("hard_session_weekday_")]
        best_hard_days = sorted(hard_probs, key=lambda p: p["execution_probability"], reverse=True)[:3]
        return {
            "as_of": as_of.isoformat(),
            "patterns": patterns,
            "feasibility": {
                "preferred_hard_weekdays": [int(p["pattern"].rsplit("_", 1)[-1]) for p in best_hard_days],
                "long_run_completion_probability": next(
                    (p["execution_probability"] for p in patterns if p["pattern"] == "long_run_shortened"),
                    None,
                ),
            },
            "note": "Adherence patterns are feasibility evidence — not accuracy.",
        }
