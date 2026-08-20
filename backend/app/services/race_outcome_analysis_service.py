"""Race outcome decomposition — richer than PB / non-PB."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..storage import DataStorage
from .ppap_metrics_service import PpapMetricsService
from .taper_planner import TaperPlanner


class RaceOutcomeAnalysisService:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._taper = TaperPlanner(db, storage, self._ppap)

    def analyze(
        self,
        activity: Activity,
        *,
        predicted_seconds: Optional[float] = None,
        expected_pace_s_per_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        day = activity.start_time.date() if hasattr(activity.start_time, "date") else date.today()
        actual_seconds = float(activity.duration or 0)
        distance_km = float(activity.distance or 0) / 1000.0 if activity.distance else None
        performance_vs_expected = None
        if predicted_seconds and predicted_seconds > 0 and actual_seconds > 0:
            performance_vs_expected = round((actual_seconds - predicted_seconds) / predicted_seconds * 100.0, 2)

        pacing_quality = self._pacing_quality(activity, expected_pace_s_per_km)
        env = self._environment_adjustment(activity)
        taper_ctx = self._taper.plan(day)
        fatigue = self._ppap.get_tsb(day - timedelta(days=1))
        confidence = 0.4
        if predicted_seconds:
            confidence += 0.2
        if pacing_quality is not None:
            confidence += 0.15
        if env.get("adjustment_pct") is not None:
            confidence += 0.1

        return {
            "activity_id": activity.activity_id,
            "race_date": day.isoformat(),
            "performance_vs_expected_pct": performance_vs_expected,
            "pacing_quality": pacing_quality,
            "environment_adjustment": env,
            "taper_context": {
                "duration_days": taper_ctx.get("duration_days"),
                "source": taper_ctx.get("source"),
                "volume_reduction_range": taper_ctx.get("volume_reduction_range"),
            },
            "recent_fatigue_tsb": fatigue,
            "distance_km": distance_km,
            "confidence": round(min(0.85, confidence), 2),
            "missing_evidence": [k for k, v in {
                "predicted_range": predicted_seconds,
                "pacing": pacing_quality,
                "weather": env.get("adjustment_pct"),
            }.items() if v is None],
            "note": "Observational race decomposition — not a causal attribution.",
        }

    def _pacing_quality(self, activity: Activity, expected_pace: Optional[float]) -> Optional[float]:
        if not activity.distance or not activity.duration or float(activity.distance) <= 0:
            return None
        pace = float(activity.duration) / (float(activity.distance) / 1000.0)
        if expected_pace and expected_pace > 0:
            drift = abs(pace - expected_pace) / expected_pace
            return round(max(0.0, min(1.0, 1.0 - drift * 2)), 3)
        # Without expected pace, use evenness proxy from avg vs max HR if present
        if activity.average_hr and activity.max_hr and float(activity.max_hr) > 0:
            ratio = float(activity.average_hr) / float(activity.max_hr)
            return round(max(0.0, min(1.0, 1.2 - abs(ratio - 0.85))), 3)
        return None

    def _environment_adjustment(self, activity: Activity) -> Dict[str, Any]:
        # Prefer weak adjustment when weather fields are missing/weak
        temp = getattr(activity, "temperature", None) or getattr(activity, "avg_temperature", None)
        if temp is None:
            return {"adjustment_pct": None, "reason": "weather_unavailable", "freshness": "missing"}
        adj = 0.0
        reason = []
        if float(temp) >= 22:
            adj += 0.02 + max(0.0, (float(temp) - 22) * 0.005)
            reason.append("heat")
        if float(temp) <= 0:
            adj += 0.01
            reason.append("cold")
        return {
            "adjustment_pct": round(adj, 3),
            "reason": ",".join(reason) or "neutral",
            "freshness": "fresh",
        }
