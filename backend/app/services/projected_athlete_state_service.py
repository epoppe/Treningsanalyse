"""Projisert tilstand for fremtidige plan-dager. Ikke observert helse-data."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .athlete_state_service import AthleteStateService
from .ppap_metrics_service import PpapMetricsService

TSS_BY_TYPE = {
    "rest": 0.0,
    "recovery_run": 25.0,
    "easy_run": 45.0,
    "long_run": 85.0,
    "steady": 60.0,
    "threshold": 80.0,
    "vo2_intervals": 90.0,
    "race_pace": 75.0,
    "strides": 40.0,
    "strength": 20.0,
    "cycling": 55.0,
    "swimming": 40.0,
}


class ProjectedAthleteStateService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._state = AthleteStateService(db, storage, self._ppap)

    def project(
        self,
        origin: date,
        target: date,
        *,
        planned_sessions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if target <= origin:
            observed = self._state.build_state(target)
            return {
                "date": target.isoformat(),
                "state_type": "observed",
                "fatigue": {"expected": (observed.get("fatigue") or {}).get("value"), "range": None},
                "readiness": {"expected": (observed.get("recovery") or {}).get("value"), "range": None},
                "uncertainty": 0.1,
                "athlete_state": observed,
            }
        # Aldri les HRV/RHR for target > origin.
        today = self._state.build_state(origin)
        ctl = self._ppap.get_ctl(origin) or 0.0
        atl = self._ppap.get_atl(origin) or 0.0
        readiness = (today.get("recovery") or {}).get("value")
        days = (target - origin).days
        planned_load = 0.0
        for session in planned_sessions or []:
            offset = session.get("day_offset")
            if offset is None:
                continue
            session_day = origin + timedelta(days=int(offset))
            if origin < session_day <= target:
                planned_load += self._session_tss(session)
        # Enkel decay + planlagt last. Usikkerhet øker med horisont.
        ctl_p = float(ctl) * (0.98 ** days) + planned_load * 0.05
        atl_p = float(atl) * (0.85 ** days) + planned_load * 0.25
        tsb_p = ctl_p - atl_p
        readiness_p = None
        if readiness is not None:
            readiness_p = float(readiness) - planned_load * 0.08 + days * 1.5
            readiness_p = max(20.0, min(95.0, readiness_p))
        uncertainty = min(0.85, 0.15 + 0.08 * days)
        half_width_r = 8 + 6 * days
        half_width_f = 5 + 4 * days
        return {
            "date": target.isoformat(),
            "state_type": "projected",
            "fatigue": {
                "expected": round(atl_p, 1),
                "range": [round(max(0.0, atl_p - half_width_f), 1), round(atl_p + half_width_f, 1)],
            },
            "readiness": {
                "expected": round(readiness_p, 1) if readiness_p is not None else None,
                "range": (
                    [
                        round(max(0.0, readiness_p - half_width_r), 1),
                        round(min(100.0, readiness_p + half_width_r), 1),
                    ]
                    if readiness_p is not None
                    else None
                ),
            },
            "projected_ctl": round(ctl_p, 1),
            "projected_tsb": round(tsb_p, 1),
            "planned_load_to_date": round(planned_load, 1),
            "uncertainty": round(uncertainty, 2),
            "note": "Projected, not observed. Future HRV/readiness was not read.",
        }

    @staticmethod
    def _session_tss(session: Dict[str, Any]) -> float:
        wtype = session.get("type") or session.get("workout_type") or "easy_run"
        return float(TSS_BY_TYPE.get(wtype, 40.0))
