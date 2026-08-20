"""Coarse 4–6 week mesocycle simulation — load/CTL/ATL/TSB sketch, not VO2/race-time."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .ppap_metrics_service import PpapMetricsService


class MesocycleSimulationService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)

    def simulate_candidates(
        self,
        candidates: Dict[str, Dict[str, Any]],
        envelope: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        out = {}
        for name, payload in candidates.items():
            out[name] = self.simulate(payload.get("weeks") or [], envelope, label=name)
        return out

    def simulate(
        self,
        weeks: list,
        envelope: Dict[str, Any],
        *,
        label: str = "balanced",
    ) -> Dict[str, Any]:
        ctl = float(envelope.get("current_load") or 40.0) * 0.4
        atl = ctl * 0.8
        series = []
        hard_density = []
        long_prog = []
        for week in weeks:
            vol = week.get("target_volume") or week.get("volume_target_min") or [0, 0]
            mid = (float(vol[0]) + float(vol[1])) / 2.0
            quality = int(week.get("quality_sessions") or 0)
            # Simple exponential load proxies (Banister-like sketch)
            ctl = ctl * 0.9 + mid * 0.1
            atl = atl * 0.7 + mid * 0.3
            tsb = ctl - atl
            intensity = "polarized" if quality <= 1 else "pyramidal"
            series.append(
                {
                    "week": week.get("week") or week.get("week_index"),
                    "weekly_load": round(mid, 1),
                    "ctl": round(ctl, 1),
                    "atl": round(atl, 1),
                    "tsb": round(tsb, 1),
                    "intensity_distribution": intensity,
                    "hard_session_density": quality,
                    "long_run_target_min": week.get("long_run_target_min"),
                }
            )
            hard_density.append(quality)
            lr = week.get("long_run_target_min") or [0, 0]
            long_prog.append((lr[0] + lr[1]) / 2.0)

        peak_atl_risk = 0.3
        if series:
            min_tsb = min(s["tsb"] for s in series)
            if min_tsb < -25:
                peak_atl_risk = 0.75
            elif min_tsb < -10:
                peak_atl_risk = 0.5
            if label == "aggressive":
                peak_atl_risk = min(0.9, peak_atl_risk + 0.15)
            # Guardrail: if aggressive exceeds envelope upper often, flag
            upper = (envelope.get("supported_next_range") or [0, 0])[1]
            if upper and any(s["weekly_load"] > float(upper) * 1.05 for s in series):
                peak_atl_risk = min(1.0, peak_atl_risk + 0.2)

        return {
            "label": label,
            "weeks": series,
            "peak_atl_risk": round(peak_atl_risk, 3),
            "mean_hard_density": round(sum(hard_density) / len(hard_density), 2) if hard_density else 0,
            "long_run_progression": long_prog,
            "note": "Coarse load sketch — not VO2max or race-time prediction.",
        }
