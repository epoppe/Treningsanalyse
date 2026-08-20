"""Simuler forventet last/CTL/ATL/TSB for en ukeplan. Ingen VO2max-prediksjon."""

from __future__ import annotations

from datetime import date
from math import exp
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .ppap_metrics_service import PpapMetricsService
from .projected_athlete_state_service import TSS_BY_TYPE

HARD = {"threshold", "vo2_intervals", "race_pace"}
EASY = {"easy_run", "recovery_run", "long_run", "strides"}
CTL_TAU = 42.0
ATL_TAU = 7.0


class PlanSimulationService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)

    def simulate(
        self,
        sessions: List[Dict[str, Any]],
        *,
        origin: date,
    ) -> Dict[str, Any]:
        ctl = float(self._ppap.get_ctl(origin) or 0.0)
        atl = float(self._ppap.get_atl(origin) or 0.0)
        loads = []
        hard_days = []
        easy_min = 0.0
        thresh_min = 0.0
        total_min = 0.0
        last_hard = -99
        spacing_ok = True
        flags: List[str] = []
        for session in sorted(sessions, key=lambda s: int(s.get("day_offset") or 0)):
            offset = int(session.get("day_offset") or 0)
            wtype = session.get("type") or "easy_run"
            tss = float(TSS_BY_TYPE.get(wtype, 40.0))
            duration = session.get("duration_min")
            minutes = duration[1] if isinstance(duration, (list, tuple)) and duration else (
                float(duration) if isinstance(duration, (int, float)) else 45.0
            )
            if wtype == "rest":
                tss = 0.0
                minutes = 0.0
            ctl = ctl * exp(-1 / CTL_TAU) + tss * (1 - exp(-1 / CTL_TAU))
            atl = atl * exp(-1 / ATL_TAU) + tss * (1 - exp(-1 / ATL_TAU))
            loads.append(tss)
            total_min += minutes
            if wtype in EASY:
                easy_min += minutes
            if wtype in HARD:
                thresh_min += minutes
                if offset - last_hard < 2:
                    spacing_ok = False
                    flags.append("hard_sessions_too_close")
                last_hard = offset
                hard_days.append(offset)
        tsb = ctl - atl
        mean_load = sum(loads) / len(loads) if loads else 0.0
        var = sum((x - mean_load) ** 2 for x in loads) / len(loads) if loads else 0.0
        std = var ** 0.5
        monotony = (mean_load / std) if std > 0.1 else None
        if monotony and monotony >= 2.0:
            flags.append("monotonous_loading")
        if tsb < -20:
            flags.append("projected_high_fatigue")
        easy_pct = round(100.0 * easy_min / total_min, 1) if total_min else None
        thresh_pct = round(100.0 * thresh_min / total_min, 1) if total_min else None
        return {
            "planned_load": round(sum(loads), 1),
            "projected_ctl": round(ctl, 1),
            "projected_atl": round(atl, 1),
            "projected_tsb": round(tsb, 1),
            "hard_sessions": len(hard_days),
            "easy_pct": easy_pct,
            "threshold_pct": thresh_pct,
            "hard_spacing_ok": spacing_ok,
            "training_monotony": round(monotony, 2) if monotony is not None else None,
            "risk_flags": flags,
            "note": "Load projection only — VO2max/performance is not simulated.",
        }
