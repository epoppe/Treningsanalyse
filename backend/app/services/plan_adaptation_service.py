"""Closed-loop justering av ukeplanen når nye data kommer — uten å endre brukerpreferanser."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .athlete_calibration_service import AthleteCalibrationService
from .ppap_metrics_service import PpapMetricsService
from .session_quality_service import SessionQualityService
from .weekly_plan_service import WeeklyPlanService


class PlanAdaptationService:
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
        self._calibration = AthleteCalibrationService(db, storage, self._ppap)
        self._quality = SessionQualityService(db, storage, self._ppap)
        self._weekly = WeeklyPlanService(db, storage, self._ppap, goal=goal)

    def assess(
        self,
        day: Optional[date] = None,
        *,
        plan: Optional[Dict[str, Any]] = None,
        goal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        day = day or date.today()
        plan = plan or self._weekly.build(day, goal=goal)
        params = self._calibration.resolve_parameters(end_date=day)
        hrv_warn = params["hrv_drop_warning_pct"]
        rhr_warn = params["rhr_rise_warning_bpm"]
        hrv = self._ppap.get_hrv_delta_pct(day)
        rhr = self._ppap.get_rhr_delta_bpm(day)
        quality = self._yesterdays_quality(day)

        reasons: List[str] = []
        changes: List[Dict[str, Any]] = []
        status = "keep"
        tomorrow = self._session_on(plan, 1) or self._session_on(plan, 0)

        hrv_hit = hrv is not None and hrv < float(hrv_warn["value"])
        rhr_hit = rhr is not None and rhr > float(rhr_warn["value"])
        quality_poor = quality is not None and quality < 50
        planned_hard = tomorrow and tomorrow.get("type") in {"threshold", "vo2_intervals", "race_pace"}

        if planned_hard and (hrv_hit or rhr_hit or quality_poor):
            status = "recovery_override" if (hrv_hit and rhr_hit) else "modify"
            delay = 48 if (hrv_hit and rhr_hit) else 24
            changes.append(
                {
                    "action": "delay_quality",
                    "hours": delay,
                    "from_type": tomorrow.get("type"),
                    "to_type": "easy_run",
                }
            )
            if hrv_hit:
                reasons.append(
                    f"HRV {hrv}% below warning {hrv_warn['value']} ({hrv_warn['threshold_source']})"
                )
            if rhr_hit:
                reasons.append(
                    f"RHR +{rhr} bpm vs warning {rhr_warn['value']} ({rhr_warn['threshold_source']})"
                )
            if quality_poor:
                reasons.append(f"yesterday session quality={quality}")
        elif not planned_hard and not hrv_hit and not rhr_hit:
            status = "keep"
            reasons.append("no_quality_conflict")

        confidence = 0.7 if hrv is not None or rhr is not None else 0.4
        return {
            "plan_status": status,
            "changes": changes,
            "reason": reasons,
            "confidence": round(confidence, 2),
            "signals": {
                "hrv_delta_pct": hrv,
                "rhr_delta_bpm": rhr,
                "yesterday_quality": quality,
            },
            "thresholds": {
                "hrv": hrv_warn,
                "rhr": rhr_warn,
            },
            "note": "Does not change permanent athlete preferences.",
        }

    def _yesterdays_quality(self, day: date) -> Optional[float]:
        yesterday = day - timedelta(days=1)
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(func.date(Activity.start_time) == yesterday)
            .all()
        )
        scores = []
        for activity in activities:
            if not is_running_activity(activity):
                continue
            q = self._quality.evaluate(activity).get("quality_score")
            if q is not None:
                scores.append(float(q))
        return sum(scores) / len(scores) if scores else None

    @staticmethod
    def _session_on(plan: Dict[str, Any], offset: int) -> Optional[Dict[str, Any]]:
        for session in plan.get("sessions") or []:
            if session.get("day_offset") == offset:
                return session
        return None
