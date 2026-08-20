"""Enkel modellhelse / drift-monitor for coaching-laget."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..storage import DataStorage
from .athlete_calibration_service import AthleteCalibrationService
from .pb_probability_calibration_service import PbProbabilityCalibrationService
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import SessionClassifierService


class CoachingModelHealthService:
    """Overvåker datakvalitet, classifier confidence og kalibreringsstøtte."""

    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self._ppap = PpapMetricsService(db, storage)
        self._classifier = SessionClassifierService(db, storage)

    def assess(self, day: Optional[date] = None) -> Dict[str, Any]:
        day = day or date.today()
        warnings: List[str] = []
        checks: Dict[str, Any] = {}

        activity_count = (
            self.db.query(func.count(Activity.activity_id))
            .filter(func.date(Activity.start_time) >= day - timedelta(days=28))
            .scalar()
            or 0
        )
        checks["activities_28d"] = activity_count
        if activity_count < 5:
            warnings.append("few_recent_activities")

        # Classifier confidence on recent runs
        recent = (
            self.db.query(Activity)
            .filter(func.date(Activity.start_time) >= day - timedelta(days=14))
            .order_by(Activity.start_time.desc())
            .limit(10)
            .all()
        )
        confidences = []
        for activity in recent:
            result = self._classifier.classify_activity(activity, end_date=day)
            if result.get("session_type") != "unknown":
                confidences.append(float(result.get("confidence") or 0))
        avg_class_conf = sum(confidences) / len(confidences) if confidences else 0.0
        checks["avg_classifier_confidence"] = round(avg_class_conf, 2)
        if confidences and avg_class_conf < 0.45:
            warnings.append("classifier_confidence_falling")

        ctl = self._ppap.get_ctl(day)
        checks["ctl_present"] = ctl is not None
        if ctl is None:
            warnings.append("missing_ctl")

        hrv = self._ppap.get_hrv_delta_pct(day)
        checks["hrv_delta_present"] = hrv is not None
        if hrv is None:
            warnings.append("missing_hrv")

        pb_cal = PbProbabilityCalibrationService(self.db, self.storage, self._ppap)
        pb_5k = pb_cal.build_calibration("5k", end_date=day)
        checks["pb_calibration_samples_5k"] = pb_5k.get("sample_count", 0)
        if pb_5k.get("sample_count", 0) < 8:
            warnings.append("pb_calibration_sparse")

        athlete_cal = AthleteCalibrationService(self.db, self.storage, self._ppap).calibrate_all(
            end_date=day
        )
        checks["personalized_parameters"] = athlete_cal.get("personalized_count", 0)

        # Recommendation distribution stability from ledger — do NOT re-enter recommend() engine
        from ..database.models.coaching_v5 import RecommendationRecord

        recent_cutoff = day - timedelta(days=28)
        prior_cutoff = day - timedelta(days=56)
        recent_rows = (
            self.db.query(RecommendationRecord.recommended_workout_type)
            .filter(
                RecommendationRecord.as_of_date >= recent_cutoff,
                RecommendationRecord.as_of_date <= day,
                RecommendationRecord.is_shadow.is_(False),
            )
            .all()
        )
        prior_rows = (
            self.db.query(RecommendationRecord.recommended_workout_type)
            .filter(
                RecommendationRecord.as_of_date >= prior_cutoff,
                RecommendationRecord.as_of_date < recent_cutoff,
                RecommendationRecord.is_shadow.is_(False),
            )
            .all()
        )
        recent_recs = [r[0] for r in recent_rows]
        prior_recs = [r[0] for r in prior_rows]
        checks["recent_recommendation_types"] = recent_recs[:8]
        checks["distribution_source"] = "recommendation_ledger"
        if recent_recs and prior_recs:
            recent_hard = sum(1 for r in recent_recs if r in {"threshold", "vo2_intervals"})
            prior_hard = sum(1 for r in prior_recs if r in {"threshold", "vo2_intervals"})
            # Compare rates to avoid raw count bias from unequal n
            recent_rate = recent_hard / max(1, len(recent_recs))
            prior_rate = prior_hard / max(1, len(prior_recs))
            if abs(recent_rate - prior_rate) >= 0.45 and len(recent_recs) >= 3:
                warnings.append("recommendation_distribution_shift")

        if activity_count == 0:
            status = "insufficient_data"
        elif len(warnings) >= 3:
            status = "degraded"
        elif warnings:
            status = "degraded" if "few_recent_activities" in warnings else "healthy"
        else:
            status = "healthy"

        # Soften: single missing HRV alone -> still healthy with warning (missing ≠ negative)
        if status == "degraded" and warnings == ["missing_hrv"]:
            status = "healthy"

        return {
            "date": day.isoformat(),
            "status": status,
            "checks": checks,
            "warnings": warnings,
        }
