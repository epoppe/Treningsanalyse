"""Simple coaching baselines for out-of-sample comparison."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .ppap_metrics_service import PpapMetricsService
from .training_availability_service import TrainingAvailabilityService


class CoachingBaselines:
    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._avail = TrainingAvailabilityService(db)

    def workout_recommendation(self, day: date) -> Dict[str, Any]:
        """easy unless sufficiently recovered + spacing + quality due."""
        readiness = self._ppap.get_readiness_component(day, "readiness.total_score")
        tsb = self._ppap.get_tsb(day)
        recovered = readiness is not None and readiness >= 60 and (tsb is None or tsb > -10)
        # Quality due every 3rd day heuristic if recovered
        quality_due = day.toordinal() % 3 == 0
        if recovered and quality_due:
            workout = "threshold"
        elif readiness is not None and readiness < 40:
            workout = "rest"
        else:
            workout = "easy_run"
        return {
            "workout_type": workout,
            "source": "baseline_easy_unless",
            "inputs": {"readiness": readiness, "tsb": tsb, "quality_due": quality_due},
        }

    def readiness_baseline(self, day: date) -> Dict[str, Any]:
        hrv = self._ppap.get_hrv_delta_pct(day)
        rhr = self._ppap.get_rhr_delta_bpm(day)
        score = 70.0
        if hrv is not None:
            score += max(-20.0, min(15.0, float(hrv)))
        if rhr is not None:
            score -= max(-10.0, min(20.0, float(rhr) * 2))
        return {
            "score": round(max(0.0, min(100.0, score)), 1),
            "source": "hrv_rhr_simple_baseline",
            "hrv_delta_pct": hrv,
            "rhr_delta_bpm": rhr,
        }

    def race_prediction(self, distance_m: float, recent_time_sec: Optional[float]) -> Dict[str, Any]:
        if not recent_time_sec or distance_m <= 0:
            return {"prediction_sec": None, "source": "unavailable"}
        # Riegel with exponent 1.06 from a known recent effort assumed at same distance proxy
        prediction = float(recent_time_sec) * ((distance_m / max(distance_m, 1)) ** 1.06)
        return {"prediction_sec": round(prediction, 1), "source": "riegel_default", "exponent": 1.06}

    def weekly_plan(self, week_start: date) -> Dict[str, Any]:
        """Simple pyramidal week respecting availability when configured."""
        sessions: List[Dict[str, Any]] = []
        constraints = self._avail.constraints_for_week(week_start)
        for offset, constraint in enumerate(constraints):
            if not constraint.get("available"):
                sessions.append({"day_offset": offset, "type": "rest", "duration_min": [0, 0]})
                continue
            if offset == 6 and constraint.get("allows_long_run"):
                sessions.append({"day_offset": offset, "type": "long_run", "duration_min": [70, 100]})
            elif offset == 2 and not constraint.get("avoid_hard"):
                sessions.append({"day_offset": offset, "type": "threshold", "duration_min": [45, 60]})
            else:
                sessions.append({"day_offset": offset, "type": "easy_run", "duration_min": [40, 60]})
        return {
            "week_start": week_start.isoformat(),
            "sessions": sessions,
            "source": "pyramidal_baseline",
        }

    def compare(self, model_metric: Optional[float], baseline_metric: Optional[float]) -> Dict[str, Any]:
        delta = None
        if model_metric is not None and baseline_metric is not None:
            delta = round(float(model_metric) - float(baseline_metric), 4)
        return {
            "model_metric": model_metric,
            "baseline_metric": baseline_metric,
            "delta": delta,
            "beats_baseline": bool(delta is not None and delta > 0),
        }
