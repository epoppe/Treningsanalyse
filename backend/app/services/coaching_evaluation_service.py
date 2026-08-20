"""Maskinlesbart evaluation payload for coaching-modellkvalitet."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..storage import DataStorage
from .calibration_report_service import CalibrationReportService
from .coaching_backtest_service import CoachingBacktestService
from .coaching_model_health_service import CoachingModelHealthService
from .pb_probability_calibration_service import PbProbabilityCalibrationService
from .recommendation_outcome_service import RecommendationOutcomeService
from .session_classifier_service import SessionClassifierService


class CoachingEvaluationService:
    """Samler accuracy, calibration, coverage og model health uten UI."""

    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage

    def build_payload(
        self,
        *,
        end_date: Optional[date] = None,
        lookback_days: int = 90,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)

        outcomes = RecommendationOutcomeService(self.db, self.storage).evaluate_period(
            start_date=start,
            end_date=end,
            step_days=7,
        )
        calibration = CalibrationReportService(self.db, self.storage).build_report(
            start_date=start,
            end_date=end,
            step_days=7,
        )
        backtest = CoachingBacktestService(self.db, self.storage).evaluate_period(
            start_date=start,
            end_date=end,
            step_days=14,
        )
        health = CoachingModelHealthService(self.db, self.storage).assess(end)
        pb = PbProbabilityCalibrationService(self.db, self.storage).build_calibration(
            "5k",
            end_date=end,
        )

        return {
            "generated_at": end.isoformat(),
            "lookback_days": lookback_days,
            "recommendation_accuracy": {
                "adherence_rate": outcomes.get("summary", {}).get("adherence_rate"),
                "evaluation_count": outcomes.get("summary", {}).get("count"),
                "note": "Adherence is not correctness; see outcome labels in evaluations.",
            },
            "session_classification_quality": {
                "avg_confidence_proxy": health.get("checks", {}).get("avg_classifier_confidence"),
                "note": "Proxy via recent classifier confidence — not labeled ground truth.",
            },
            "confidence_calibration": calibration,
            "trend_stability": {
                "backtest_summary": backtest.get("summary"),
            },
            "pb_calibration": pb,
            "data_coverage": {
                "activities_28d": health.get("checks", {}).get("activities_28d"),
                "ctl_present": health.get("checks", {}).get("ctl_present"),
                "hrv_present": health.get("checks", {}).get("hrv_delta_present"),
            },
            "model_health": health,
        }
