"""Overvåk kalibrerings- og anbefalingsdrift. Unstable → fallback mot defaults."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import pstdev
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.models.coaching_v5 import CalibrationSnapshot, RecommendationRecord


class PersonalizationStabilityService:
    def __init__(self, db: Session):
        self.db = db

    def assess(self, *, as_of_date: Optional[date] = None) -> Dict[str, Any]:
        as_of_date = as_of_date or date.today()
        flags: List[str] = []
        param_vol = self._parameter_volatility()
        if param_vol >= 0.35:
            flags.append("calibration_volatility")
        rec_shift = self._recommendation_distribution_shift(as_of_date)
        if rec_shift:
            flags.append("recommendation_distribution_shift")
        if self._prescription_churn():
            flags.append("prescription_changes")
        if param_vol >= 0.22:
            flags.append("threshold_drift")

        if "calibration_volatility" in flags and rec_shift:
            status = "unstable"
        elif flags:
            status = "watch"
        else:
            status = "stable"
        return {
            "status": status,
            "as_of_date": as_of_date.isoformat(),
            "parameter_volatility": round(param_vol, 3),
            "flags": flags,
            "fallback_to_defaults": status == "unstable",
            "note": "Unstable personalization falls back toward defaults. Not a diagnosis.",
        }

    def _parameter_volatility(self) -> float:
        names = {row.parameter for row in self.db.query(CalibrationSnapshot.parameter).distinct()}
        vols = []
        for name in names:
            rows = (
                self.db.query(CalibrationSnapshot)
                .filter(CalibrationSnapshot.parameter == name)
                .order_by(CalibrationSnapshot.calculated_at.desc())
                .limit(6)
                .all()
            )
            values = []
            for row in rows:
                val = row.effective_value_json
                if isinstance(val, (int, float)):
                    values.append(float(val))
                elif isinstance(val, list) and val and isinstance(val[0], (int, float)):
                    values.append(float(val[0]))
            if len(values) >= 3:
                mean_v = abs(sum(values) / len(values)) or 1.0
                vols.append(pstdev(values) / mean_v)
        return max(vols) if vols else 0.0

    def _recommendation_distribution_shift(self, as_of_date: date) -> bool:
        recent = self._types(as_of_date - timedelta(days=27), as_of_date)
        prior = self._types(as_of_date - timedelta(days=55), as_of_date - timedelta(days=28))
        if len(recent) < 4 or len(prior) < 4:
            return False
        hard = {"threshold", "vo2_intervals", "race_pace"}
        recent_hard = sum(1 for t in recent if t in hard) / len(recent)
        prior_hard = sum(1 for t in prior if t in hard) / len(prior)
        return abs(recent_hard - prior_hard) >= 0.4

    def _prescription_churn(self) -> bool:
        rows = (
            self.db.query(RecommendationRecord)
            .order_by(RecommendationRecord.generated_at.desc())
            .limit(8)
            .all()
        )
        hashes = []
        for row in rows:
            rx = row.workout_prescription_json or {}
            hashes.append((row.recommended_workout_type, rx.get("structure"), rx.get("total_duration_min")))
        return len(set(hashes)) >= 7 and len(hashes) >= 7

    def _types(self, start: date, end: date) -> List[str]:
        rows = (
            self.db.query(RecommendationRecord.recommended_workout_type)
            .filter(
                RecommendationRecord.as_of_date >= start,
                RecommendationRecord.as_of_date <= end,
            )
            .all()
        )
        return [r[0] for r in rows if r[0]]
