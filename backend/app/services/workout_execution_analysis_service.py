"""Sammenlign prescribed workout mot faktiske lap/FIT-data."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.activity import Activity, ActivityLap
from ..storage import DataStorage


class WorkoutExecutionAnalysisService:
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage

    def analyze(self, activity: Activity, prescription: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        prescription = prescription or {}
        main = prescription.get("main_set") or {}
        laps = self._laps(activity)
        work_laps = [lap for lap in laps if self._is_work_lap(lap, main)]
        planned_reps = main.get("repetitions") or 1
        planned_work_s = float(main.get("work_duration_min") or 0) * 60.0
        planned_rec_s = float(main.get("recovery_duration_min") or 0) * 60.0
        target_hr = main.get("target_hr")

        completion = None
        if planned_reps and planned_work_s > 0 and work_laps:
            completed = 0
            for lap in work_laps[: int(planned_reps)]:
                if lap.duration and float(lap.duration) >= planned_work_s * 0.8:
                    completed += 1
            completion = round(100.0 * completed / float(planned_reps), 1)
        elif activity.duration and prescription.get("total_duration_min"):
            completion = min(
                100.0,
                round(100.0 * (float(activity.duration) / 60.0) / float(prescription["total_duration_min"]), 1),
            )

        intensity_pct = None
        if target_hr and isinstance(target_hr, (list, tuple)) and len(target_hr) >= 2:
            lo, hi = float(target_hr[0]), float(target_hr[1])
            hrs = [float(lap.average_heart_rate) for lap in work_laps if lap.average_heart_rate]
            if not hrs and activity.average_heart_rate:
                hrs = [float(activity.average_heart_rate)]
            if hrs:
                in_zone = sum(1 for hr in hrs if lo <= hr <= hi + 3)
                intensity_pct = round(100.0 * in_zone / len(hrs), 1)

        consistency = None
        durs = [float(lap.duration) for lap in work_laps if lap.duration]
        if len(durs) >= 2:
            mean_d = sum(durs) / len(durs)
            if mean_d > 0:
                cv = (sum((d - mean_d) ** 2 for d in durs) / len(durs)) ** 0.5 / mean_d
                consistency = round(max(0.0, 100.0 - cv * 200.0), 1)

        rec_ok = None
        rec_laps = [lap for lap in laps if lap not in work_laps]
        if planned_rec_s > 0 and rec_laps:
            rec_durs = [float(lap.duration) for lap in rec_laps if lap.duration]
            if rec_durs:
                rec_ok = round(sum(rec_durs) / len(rec_durs) / planned_rec_s * 100.0, 1)

        planned_load = prescription.get("total_duration_min")
        actual_load = (float(activity.duration) / 60.0) if activity.duration else None
        deviations: List[str] = []
        if completion is not None and completion < 80:
            deviations.append("incomplete_main_set")
        if intensity_pct is not None and intensity_pct < 60:
            deviations.append("below_target_intensity")
        if consistency is not None and consistency < 50:
            deviations.append("inconsistent_intervals")

        execution_quality = None
        parts = [p for p in (completion, intensity_pct, consistency) if p is not None]
        if parts:
            execution_quality = round(sum(parts) / len(parts), 1)

        return {
            "completion_pct": completion,
            "target_intensity_pct": intensity_pct,
            "interval_consistency": consistency,
            "recovery_duration_pct": rec_ok,
            "planned_vs_actual_load": {
                "planned_min": planned_load,
                "actual_min": round(actual_load, 1) if actual_load is not None else None,
            },
            "execution_quality": execution_quality,
            "deviations": deviations,
            "distinctions": {
                "workout_design_quality": "not_inferred_here",
                "execution_quality": execution_quality,
                "physiological_response": "not_inferred_here",
            },
        }

    def _laps(self, activity: Activity) -> List[ActivityLap]:
        if activity.laps:
            return sorted(activity.laps, key=lambda lap: lap.lap_number or 0)
        return (
            self.db.query(ActivityLap)
            .filter(ActivityLap.activity_id == activity.activity_id)
            .order_by(ActivityLap.lap_number)
            .all()
        )

    @staticmethod
    def _is_work_lap(lap: ActivityLap, main: Dict[str, Any]) -> bool:
        planned = float(main.get("work_duration_min") or 0) * 60.0
        if planned <= 0:
            return True
        if not lap.duration:
            return False
        return float(lap.duration) >= planned * 0.5
