"""Transparent personal recovery-cost ranges — default vs observed evidence."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import AthleteFeedback, RecommendationExecution, RecommendationRecord
from .personalization_evidence_policy import PersonalizationEvidencePolicy
from .ppap_metrics_service import PpapMetricsService
from .evidence_hierarchy import EvidenceHierarchy
from .status_semantics import SourceType


DEFAULT_RANGES = {
    "easy_run": {"expected_recovery_days": [0, 1], "confidence": "moderate"},
    "recovery_run": {"expected_recovery_days": [0, 1], "confidence": "moderate"},
    "long_run": {"expected_recovery_days": [1, 2], "confidence": "moderate"},
    "threshold": {"expected_recovery_days": [1, 2], "confidence": "moderate"},
    "vo2_intervals": {"expected_recovery_days": [1, 3], "confidence": "moderate"},
    "race_pace": {"expected_recovery_days": [1, 2], "confidence": "low"},
    "race": {"expected_recovery_days": [3, 7], "confidence": "moderate"},
    "strength": {"expected_recovery_days": [1, 2], "confidence": "low"},
    "cycling": {"expected_recovery_days": [0, 1], "confidence": "low"},
}

MIN_PERSONAL_SAMPLES = 8


class RecoveryCostService:
    """
    Recovery cost envelopes.

    source:
      - default: population/config envelope (not personalized)
      - historical: linked executions with recovery markers
      - prospective: recommendation→execution closed-loop with feedback
    Only historical/prospective may be labeled personalized.
    """

    def __init__(self, db: Session, ppap: Optional[PpapMetricsService] = None):
        self.db = db
        self._ppap = ppap or PpapMetricsService(db, None)
        self._policy = PersonalizationEvidencePolicy()
        self._hierarchy = EvidenceHierarchy()

    def estimate(self, workout_type: str, *, as_of: Optional[date] = None) -> Dict[str, Any]:
        as_of = as_of or date.today()
        base = dict(
            DEFAULT_RANGES.get(
                workout_type, {"expected_recovery_days": [1, 2], "confidence": "low"}
            )
        )
        observed = self._observed_recovery_days(workout_type, as_of)
        hierarchy = self._hierarchy.resolve(
            domain="recovery_cost",
            prospective_n=observed.get("prospective_n", 0),
            historical_n=observed.get("historical_n", 0),
            prospective_dates=observed.get("prospective_dates"),
            historical_dates=observed.get("historical_dates"),
            as_of=as_of,
        )
        level = self._policy.assess(
            sample_count=observed["sample_count"],
            evidence_strength=observed.get("evidence_strength", 0.0),
            prospective=hierarchy["source"] == "prospective",
            as_of=as_of,
            last_supporting_observation=observed.get("last_observation"),
        )

        if hierarchy["personalized"] and level["may_override_defaults"] and observed.get("range"):
            return {
                "workout_type": workout_type,
                "expected_recovery_days": observed["range"],
                "range": observed["range"],
                "confidence": "high" if level["level"] == "PERSONAL_STRONG" else "moderate",
                "source": hierarchy["source"],
                "personalized": True,
                "sample_count": observed["sample_count"],
                "effective_sample_count": hierarchy["effective_sample_count"],
                "evidence_level": hierarchy["evidence_level"],
                "evidence_strength": level["evidence_strength"],
                "personalization_level": level["level"],
                "ci": observed.get("ci"),
                "source_type": SourceType.DERIVED_FROM_OBSERVED.value,
                "note": "Personalized range from session dose + HRV/RHR/feedback — not causal.",
            }

        return {
            "workout_type": workout_type,
            "expected_recovery_days": base["expected_recovery_days"],
            "range": base["expected_recovery_days"],
            "confidence": base["confidence"],
            "source": "default",
            "personalized": False,
            "sample_count": observed["sample_count"],
            "effective_sample_count": hierarchy["effective_sample_count"],
            "evidence_level": hierarchy["evidence_level"],
            "evidence_strength": level["evidence_strength"],
            "personalization_level": level["level"],
            "ci": None,
            "source_type": SourceType.CONFIG.value,
            "note": "Default recovery envelope — not personalized until SampleSufficiencyPolicy allows.",
        }

    def summary(self, *, as_of: Optional[date] = None) -> Dict[str, Any]:
        types = ["easy_run", "long_run", "threshold", "vo2_intervals", "race", "strength", "cycling"]
        return {t: self.estimate(t, as_of=as_of) for t in types}

    def _observed_recovery_days(self, workout_type: str, as_of: date) -> Dict[str, Any]:
        rows = (
            self.db.query(RecommendationExecution, RecommendationRecord, Activity)
            .outerjoin(
                RecommendationRecord,
                RecommendationExecution.recommendation_id == RecommendationRecord.id,
            )
            .outerjoin(Activity, RecommendationExecution.activity_id == Activity.activity_id)
            .limit(300)
            .all()
        )
        days_list: List[float] = []
        prospective_dates: List[date] = []
        historical_dates: List[date] = []
        last_obs: Optional[date] = None

        for exec_row, rec, activity in rows:
            planned = exec_row.planned_type or (rec.recommended_workout_type if rec else None)
            if planned != workout_type:
                continue
            act_day = self._activity_day(activity, exec_row)
            if act_day is None or act_day > as_of:
                continue
            recovery_days = self._estimate_days_to_recover(act_day, exec_row, activity)
            if recovery_days is None:
                continue
            days_list.append(float(recovery_days))
            last_obs = act_day if last_obs is None else max(last_obs, act_day)
            if exec_row.recommendation_id is not None:
                prospective_dates.append(act_day)
            else:
                historical_dates.append(act_day)

        n = len(days_list)
        prospective_n = len(prospective_dates)
        historical_n = len(historical_dates)
        if n < 3:
            return {
                "sample_count": n,
                "range": None,
                "source": "default",
                "evidence_strength": 0.1 * n,
                "last_observation": last_obs,
                "ci": None,
                "prospective_n": prospective_n,
                "historical_n": historical_n,
                "prospective_dates": prospective_dates,
                "historical_dates": historical_dates,
            }

        days_list.sort()
        lo = int(max(0, days_list[0]))
        hi = int(max(lo + 1, round(days_list[-1])))
        mid = median(days_list)
        p25 = days_list[max(0, n // 4)]
        p75 = days_list[min(n - 1, (3 * n) // 4)]
        source = "prospective" if prospective_n >= max(3, n // 2) else "historical"
        strength = min(0.85, 0.25 + 0.05 * n)
        return {
            "sample_count": n,
            "range": [lo, hi],
            "source": source,
            "evidence_strength": strength,
            "last_observation": last_obs,
            "ci": {"p25": round(p25, 2), "median": round(mid, 2), "p75": round(p75, 2)},
            "prospective_n": prospective_n,
            "historical_n": historical_n,
            "prospective_dates": prospective_dates,
            "historical_dates": historical_dates,
        }

    def _estimate_days_to_recover(
        self,
        act_day: date,
        exec_row: RecommendationExecution,
        activity: Optional[Activity],
    ) -> Optional[float]:
        """Observed lag until HRV/RHR markers improve, with feedback/dose context."""
        feedback = None
        if activity is not None:
            feedback = (
                self.db.query(AthleteFeedback)
                .filter(AthleteFeedback.activity_id == activity.activity_id)
                .order_by(AthleteFeedback.recorded_at.desc())
                .first()
            )

        # Session dose from prescription when available
        dose = None
        if exec_row.analysis_json and isinstance(exec_row.analysis_json, dict):
            dose = exec_row.analysis_json.get("session_dose")
        if dose is None and activity is not None:
            load = activity.training_stress_score or activity.epoc
            if load is not None:
                dose = {"cardiovascular_load": float(load)}

        markers: List[Tuple[int, float]] = []
        for lag in (1, 2, 3):
            d = act_day + timedelta(days=lag)
            hrv = self._ppap.get_hrv_delta_pct(d)
            rhr = self._ppap.get_rhr_delta_bpm(d)
            if hrv is None and rhr is None:
                continue
            score = 0.0
            n = 0
            if hrv is not None:
                score += float(hrv)
                n += 1
            if rhr is not None:
                score += -float(rhr)
                n += 1
            markers.append((lag, score / max(1, n)))

        if not markers and feedback is None and exec_row.overall_adherence is None:
            return None

        if markers:
            # First day markers are non-negative ≈ recovered
            for lag, score in markers:
                if score >= -2.0:
                    days = float(lag)
                    break
            else:
                days = float(markers[-1][0] + 1)
        elif exec_row.overall_adherence is not None and exec_row.overall_adherence < 0.6:
            days = 2.0
        else:
            days = 1.0

        if feedback is not None:
            if feedback.rpe is not None and feedback.rpe >= 8:
                days = max(days, 2.0)
            if feedback.pain is not None and feedback.pain >= 3:
                days = max(days, 2.0)
            if feedback.session_feel == "poor":
                days = max(days, 1.5)

        if dose and isinstance(dose, dict):
            cv = dose.get("cardiovascular_load")
            if cv is not None and float(cv) > 80:
                days = max(days, 2.0)

        return days

    @staticmethod
    def _activity_day(
        activity: Optional[Activity], exec_row: RecommendationExecution
    ) -> Optional[date]:
        if activity is not None and activity.start_time is not None:
            return activity.start_time.date() if hasattr(activity.start_time, "date") else None
        if exec_row.linked_at is not None:
            ts = exec_row.linked_at
            return ts.date() if isinstance(ts, datetime) else None
        return None
