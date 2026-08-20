"""Detect concept drift in athlete response relationships — no auto model change."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .ppap_metrics_service import PpapMetricsService
from .statistical_uncertainty import evidence_band


class AthleteConceptDriftService:
    PAIRS = (
        ("pace_hr", "Pace↔HR coupling"),
        ("load_recovery", "Load↔recovery"),
        ("rpe_load", "RPE↔objective load"),
    )

    def __init__(self, db: Session, ppap: Optional[PpapMetricsService] = None):
        self.db = db
        self._ppap = ppap or PpapMetricsService(db, None)

    def assess(self, day: Optional[date] = None, *, window_days: int = 56) -> Dict[str, Any]:
        day = day or date.today()
        recent = self._window_signals(day - timedelta(days=window_days), day)
        prior = self._window_signals(day - timedelta(days=2 * window_days), day - timedelta(days=window_days))
        results = []
        for key, label in self.PAIRS:
            status, detail = self._compare(key, recent, prior)
            results.append({"relationship": key, "label": label, "status": status, **detail})

        confirmed = sum(1 for r in results if r["status"] == "confirmed_drift")
        possible = sum(1 for r in results if r["status"] == "possible_drift")
        overall = "stable"
        if confirmed:
            overall = "confirmed_drift"
        elif possible:
            overall = "possible_drift"
        return {
            "as_of": day.isoformat(),
            "overall": overall,
            "relationships": results,
            "action": "consider_recalibration" if overall == "confirmed_drift" else "none",
            "note": "Drift triggers recalibration consideration — never automatic aggressive model change.",
        }

    def _window_signals(self, start: date, end: date) -> Dict[str, List[float]]:
        out = {"pace_hr": [], "load_recovery": [], "rpe_load": []}
        cur = start
        while cur <= end:
            tsb = self._ppap.get_tsb(cur)
            hrv = self._ppap.get_hrv_delta_pct(cur)
            ctl = self._ppap.get_ctl(cur)
            if tsb is not None and hrv is not None:
                out["load_recovery"].append(float(tsb) - float(hrv))
            if ctl is not None and tsb is not None:
                out["pace_hr"].append(float(ctl) + float(tsb))  # coarse proxy coupling
                out["rpe_load"].append(float(ctl))
            cur += timedelta(days=7)
        return out

    def _compare(self, key: str, recent: Dict, prior: Dict) -> Tuple[str, Dict[str, Any]]:
        a = recent.get(key) or []
        b = prior.get(key) or []
        if len(a) < 4 or len(b) < 4:
            return "stable", {"sample_recent": len(a), "sample_prior": len(b), "reason": "insufficient_n"}
        mean_a = sum(a) / len(a)
        mean_b = sum(b) / len(b)
        denom = max(1.0, abs(mean_b))
        delta = abs(mean_a - mean_b) / denom
        band = evidence_band(sample_count=min(len(a), len(b)), effect_size=delta)
        if delta >= 0.35 and band in {"moderate", "strong"}:
            return "confirmed_drift", {"delta": round(delta, 3), "statistical_support": band}
        if delta >= 0.2:
            return "possible_drift", {"delta": round(delta, 3), "statistical_support": band}
        return "stable", {"delta": round(delta, 3), "statistical_support": band}
