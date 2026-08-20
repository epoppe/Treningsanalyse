"""Validerer om confidence-scores matcher empirisk treffsikkerhet."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .recommendation_outcome_service import RecommendationOutcomeService

CONFIDENCE_BINS: Tuple[Tuple[float, float], ...] = (
    (0.0, 0.5),
    (0.5, 0.7),
    (0.7, 0.85),
    (0.85, 1.01),
)


class CalibrationReportService:
    """Sammenligner prediksjonsconfidence med faktisk adherence/outcome."""

    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self._outcomes = RecommendationOutcomeService(db, storage)

    def build_report(
        self,
        *,
        start_date: date,
        end_date: date,
        step_days: int = 7,
    ) -> Dict[str, Any]:
        period = self._outcomes.evaluate_period(
            start_date=start_date,
            end_date=end_date,
            step_days=step_days,
        )
        evaluations = period.get("evaluations", [])

        bins: List[Dict[str, Any]] = []
        for low, high in CONFIDENCE_BINS:
            subset = [
                e
                for e in evaluations
                if e.get("recommendation_confidence") is not None
                and low <= float(e["recommendation_confidence"]) < high
                and e.get("adherence") is not None
            ]
            if not subset:
                bins.append(
                    {
                        "confidence_min": low,
                        "confidence_max": high,
                        "expected_confidence": round((low + high) / 2, 2),
                        "empirical_success_rate": None,
                        "calibration_error": None,
                        "sample_count": 0,
                    }
                )
                continue
            success = sum(1 for e in subset if e.get("outcome") == "favorable_response")
            # Prefer outcome when available; fall back to adherence as weak proxy labeled as such
            if any(e.get("outcome") != "inconclusive" for e in subset):
                rate = success / len(subset)
                success_metric = "favorable_outcome_rate"
            else:
                rate = sum(1 for e in subset if e["adherence"]) / len(subset)
                success_metric = "adherence_rate_proxy"
            expected = (low + high) / 2
            bins.append(
                {
                    "confidence_min": low,
                    "confidence_max": high,
                    "expected_confidence": round(expected, 2),
                    "empirical_success_rate": round(rate, 3),
                    "calibration_error": round(abs(expected - rate), 3),
                    "sample_count": len(subset),
                    "success_metric": success_metric,
                }
            )

        valid = [b for b in bins if b["sample_count"] >= 3]
        mean_error = (
            sum(b["calibration_error"] for b in valid) / len(valid) if valid else None
        )
        calibrated = mean_error is not None and mean_error < 0.25 and len(valid) >= 2

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "bins": bins,
            "mean_calibration_error": round(mean_error, 3) if mean_error is not None else None,
            "is_calibrated": calibrated,
            "label_recommendation": (
                "confidence"
                if calibrated
                else "evidence_strength — historical calibration insufficient or misaligned"
            ),
            "evaluation_count": len(evaluations),
            "limitations": [
                "adherence_is_not_correctness",
                "favorable_outcome_is_observational",
            ],
        }
