"""Concept drift using real observed relationships — no CTL/TSB proxies for pace↔HR."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from ..database.models.activity import Activity
from ..database.models.coaching_v5 import AthleteFeedback
from ..utils.activity_filters import is_running_activity
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import SessionClassifierService
from .statistical_uncertainty import evidence_band
from .status_semantics import DriftStatus


MIN_SAMPLES_PER_WINDOW = 4
EXCLUDE_SESSION_TYPES = {"race", "vo2_intervals", "anaerobic", "threshold", "tempo"}
HILLY_M_PER_KM = 15.0


class AthleteConceptDriftService:
    """
    Relationships measured only from observations matching their names.

    pace_hr: average_speed / average_HR on comparable easy/steady runs
    load_recovery: session load → next-day HRV/RHR (explicit lag)
    rpe_load: AthleteFeedback.rpe vs TSS/EPOC — insufficient_data without RPE
    """

    def __init__(self, db: Session, ppap: Optional[PpapMetricsService] = None):
        self.db = db
        self._ppap = ppap or PpapMetricsService(db, None)
        self._classifier = SessionClassifierService(db, None)

    def assess(self, day: Optional[date] = None, *, window_days: int = 56) -> Dict[str, Any]:
        day = day or date.today()
        recent_start = day - timedelta(days=window_days)
        prior_start = day - timedelta(days=2 * window_days)
        prior_end = recent_start - timedelta(days=1)

        recent = {
            "pace_hr": self._pace_hr_signals(recent_start, day),
            "load_recovery": self._load_recovery_signals(recent_start, day),
            "rpe_load": self._rpe_load_signals(recent_start, day),
        }
        prior = {
            "pace_hr": self._pace_hr_signals(prior_start, prior_end),
            "load_recovery": self._load_recovery_signals(prior_start, prior_end),
            "rpe_load": self._rpe_load_signals(prior_start, prior_end),
        }

        results = []
        for key, label in (
            ("pace_hr", "Pace↔HR coupling"),
            ("load_recovery", "Load↔recovery"),
            ("rpe_load", "RPE↔objective load"),
        ):
            status, detail = self._compare(key, recent[key], prior[key])
            results.append({"relationship": key, "label": label, "status": status, **detail})

        statuses = [r["status"] for r in results]
        if DriftStatus.CONFIRMED_DRIFT.value in statuses:
            overall = DriftStatus.CONFIRMED_DRIFT.value
        elif DriftStatus.POSSIBLE_DRIFT.value in statuses:
            overall = DriftStatus.POSSIBLE_DRIFT.value
        elif DriftStatus.STABLE.value in statuses:
            overall = DriftStatus.STABLE.value
        else:
            overall = DriftStatus.INSUFFICIENT_DATA.value

        return {
            "as_of": day.isoformat(),
            "overall": overall,
            "relationships": results,
            "action": "consider_recalibration" if overall == DriftStatus.CONFIRMED_DRIFT.value else "none",
            "note": (
                "Drift uses observed pace/HR, load→recovery lag, and RPE↔load only. "
                "Insufficient evidence is never reported as stable."
            ),
        }

    def _pace_hr_signals(self, start: date, end: date) -> Dict[str, Any]:
        activities = self._running_activities(start, end)
        values: List[float] = []
        used = 0
        excluded = 0
        for act in activities:
            if not act.average_speed or not act.average_heart_rate:
                continue
            speed = float(act.average_speed)
            hr = float(act.average_heart_rate)
            if speed <= 0 or hr < 80:
                continue
            session = self._safe_classify(act, end)
            if session in EXCLUDE_SESSION_TYPES:
                excluded += 1
                continue
            if self._too_hilly(act):
                excluded += 1
                continue
            # Coupling: m/s per bpm — within-athlete comparable easy runs
            values.append(speed / hr)
            used += 1
        return {
            "values": values,
            "sample_count": used,
            "excluded": excluded,
            "variables": ["average_speed", "average_heart_rate"],
            "exclusions": list(EXCLUDE_SESSION_TYPES) + ["hilly_routes"],
        }

    def _load_recovery_signals(self, start: date, end: date) -> Dict[str, Any]:
        activities = self._running_activities(start, end)
        values: List[float] = []
        for act in activities:
            load = act.training_stress_score or act.epoc
            if load is None or float(load) <= 0:
                continue
            act_day = act.start_time.date() if hasattr(act.start_time, "date") else None
            if act_day is None:
                continue
            next_day = act_day + timedelta(days=1)
            if next_day > end + timedelta(days=1):
                continue
            hrv = self._ppap.get_hrv_delta_pct(next_day)
            rhr = self._ppap.get_rhr_delta_bpm(next_day)
            # Require at least one observed recovery marker (missing ≠ negative)
            if hrv is None and rhr is None:
                continue
            recovery = 0.0
            n = 0
            if hrv is not None:
                recovery += float(hrv)
                n += 1
            if rhr is not None:
                recovery += -float(rhr)  # elevated RHR is worse recovery
                n += 1
            recovery /= max(1, n)
            # Higher load with worse next-day recovery → lower score
            values.append(recovery / math.log1p(float(load)))
        return {
            "values": values,
            "sample_count": len(values),
            "lag_days": 1,
            "variables": ["training_stress_score|epoc", "hrv_delta_pct", "rhr_delta_bpm"],
        }

    def _rpe_load_signals(self, start: date, end: date) -> Dict[str, Any]:
        feedback_rows = (
            self.db.query(AthleteFeedback, Activity)
            .join(Activity, AthleteFeedback.activity_id == Activity.activity_id)
            .filter(AthleteFeedback.rpe.isnot(None))
            .all()
        )
        values: List[float] = []
        for fb, act in feedback_rows:
            if act.start_time is None:
                continue
            act_day = act.start_time.date() if hasattr(act.start_time, "date") else None
            if act_day is None or act_day < start or act_day > end:
                continue
            load = act.training_stress_score or act.epoc
            if load is None or float(load) <= 0:
                continue
            rpe = float(fb.rpe)
            values.append(rpe / math.log1p(float(load)))
        return {
            "values": values,
            "sample_count": len(values),
            "variables": ["athlete_feedback.rpe", "training_stress_score|epoc"],
            "requires": "athlete_feedback.rpe",
        }

    def _compare(self, key: str, recent: Dict[str, Any], prior: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        a = recent.get("values") or []
        b = prior.get("values") or []
        meta = {
            "sample_recent": len(a),
            "sample_prior": len(b),
            "variables": recent.get("variables") or prior.get("variables"),
            "lag_days": recent.get("lag_days"),
        }
        if key == "rpe_load" and (recent.get("sample_count", 0) + prior.get("sample_count", 0)) == 0:
            return DriftStatus.INSUFFICIENT_DATA.value, {
                **meta,
                "reason": "no_rpe_feedback",
                "note": "RPE drift cannot run without AthleteFeedback.rpe — no proxy manufactured.",
            }
        if len(a) < MIN_SAMPLES_PER_WINDOW or len(b) < MIN_SAMPLES_PER_WINDOW:
            return DriftStatus.INSUFFICIENT_DATA.value, {
                **meta,
                "reason": "insufficient_n",
                "min_samples_per_window": MIN_SAMPLES_PER_WINDOW,
            }
        mean_a = sum(a) / len(a)
        mean_b = sum(b) / len(b)
        denom = max(1e-6, abs(mean_b))
        delta = abs(mean_a - mean_b) / denom
        band = evidence_band(sample_count=min(len(a), len(b)), effect_size=delta)
        detail = {**meta, "delta": round(delta, 3), "statistical_support": band}
        if delta >= 0.35 and band in {"moderate", "strong"}:
            return DriftStatus.CONFIRMED_DRIFT.value, detail
        if delta >= 0.2:
            return DriftStatus.POSSIBLE_DRIFT.value, detail
        return DriftStatus.STABLE.value, detail

    def _running_activities(self, start: date, end: date) -> List[Activity]:
        rows = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    Activity.start_time >= start.isoformat(),
                    Activity.start_time < (end + timedelta(days=1)).isoformat(),
                )
            )
            .all()
        )
        return [a for a in rows if is_running_activity(a)]

    def _safe_classify(self, activity: Activity, end: date) -> str:
        try:
            result = self._classifier.classify_activity(activity, end_date=end)
            return str(result.get("session_type") or "unknown")
        except Exception:
            return "unknown"

    @staticmethod
    def _too_hilly(activity: Activity) -> bool:
        if not activity.total_ascent or not activity.distance or float(activity.distance) <= 0:
            return False
        m_per_km = float(activity.total_ascent) / (float(activity.distance) / 1000.0)
        return m_per_km >= HILLY_M_PER_KM
