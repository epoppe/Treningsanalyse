"""Deload need — not automatic every fourth week."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..schemas.coaching import DeloadNeed, coerce_enum
from ..storage import DataStorage
from .athlete_feedback_service import AthleteFeedbackService
from .load_variability_service import LoadVariabilityService
from .ppap_metrics_service import PpapMetricsService
from .training_phase_service import TrainingPhaseService


class DeloadNeedService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._load = LoadVariabilityService(db, storage, self._ppap)
        self._phase = TrainingPhaseService(db, storage, self._ppap)
        self._feedback = AthleteFeedbackService(db)

    def assess(self, day: Optional[date] = None) -> Dict[str, Any]:
        day = day or date.today()
        load = self._load.analyze(day)
        phase = self._phase.determine(day)
        hrv = self._ppap.get_hrv_delta_pct(day)
        rhr = self._ppap.get_rhr_delta_bpm(day)
        tsb = self._ppap.get_tsb(day)
        flags = load.get("flags") or []
        recent_fb = self._feedback.recent(limit=5)
        high_rpe = sum(1 for f in recent_fb if (f.get("rpe") or 0) >= 8)
        evidence = []
        score = 0
        if "monotonous_loading" in flags:
            score += 2
            evidence.append("monotony")
        if "rapid_load_change" in flags or "high_hard_session_density" in flags:
            score += 2
            evidence.append("accumulated_or_dense_load")
        if hrv is not None and hrv < -10:
            score += 2
            evidence.append("hrv_suppressed")
        if rhr is not None and rhr > 4:
            score += 1
            evidence.append("rhr_elevated")
        if tsb is not None and tsb < -20:
            score += 2
            evidence.append("fatigue_tsb")
        if high_rpe >= 3:
            score += 2
            evidence.append("rpe_drift")
        if (phase.get("phase") or "") == "recovery":
            score = max(score, 3)
            evidence.append("recovery_phase")

        if score >= 5:
            need = DeloadNeed.RECOMMENDED
        elif score >= 3:
            need = DeloadNeed.CONSIDER
        else:
            need = DeloadNeed.NOT_NEEDED
        return {
            "date": day.isoformat(),
            "deload_need": need.value,
            "score": score,
            "evidence": evidence,
            "note": "Not a fixed every-fourth-week rule.",
        }
