"""Individuelle beslutningsterskler med streng evidensgate."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median, pstdev
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..database.models import HRV, RestingHeartRate
from ..database.models.activity import Activity
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .metric_evidence import confidence_from_sample_count
from .coaching_session_types import HARD_SESSION_TYPES
from .ppap_metrics_service import PpapMetricsService
from .session_classifier_service import SessionClassifierService
from .session_quality_service import SessionQualityService

MIN_SAMPLES_PERSONALIZE = 12
MAX_CV_FOR_PERSONALIZE = 0.45

DEFAULTS: Dict[str, float] = {
    "hrv_drop_warning_pct": -12.0,
    "rhr_rise_warning_bpm": 4.0,
    "tsb_hard_session_min": -8.0,
    "tsb_hard_session_max": 12.0,
    "hard_session_spacing_hours": 36.0,
    "acwr_caution": 1.4,
    "easy_volume_min_min_per_week": 150.0,
    "threshold_density_max_pct": 15.0,
}


class AthleteCalibrationService:
    """Erstatter generelle terskler kun når evidensen er sterk nok."""

    def __init__(
        self,
        db: Session,
        storage: Optional[DataStorage] = None,
        ppap: Optional[PpapMetricsService] = None,
    ):
        self.db = db
        self.storage = storage
        self._ppap = ppap or PpapMetricsService(db, storage)
        self._classifier = SessionClassifierService(db, storage)
        self._quality = SessionQualityService(db, storage, self._ppap)

    def calibrate_all(
        self,
        *,
        end_date: Optional[date] = None,
        lookback_days: int = 365,
    ) -> Dict[str, Any]:
        end = end_date or date.today()
        start = end - timedelta(days=lookback_days)
        parameters = [
            self.calibrate_hrv_drop(start, end),
            self.calibrate_rhr_rise(start, end),
            self.calibrate_tsb_for_hard(start, end),
            self.calibrate_hard_spacing(start, end),
            self.calibrate_acwr_tolerance(start, end),
            self.calibrate_threshold_density(start, end),
        ]
        return {
            "end_date": end.isoformat(),
            "lookback_days": lookback_days,
            "parameters": parameters,
            "personalized_count": sum(1 for p in parameters if p.get("use_personalized")),
        }

    def calibrate_hrv_drop(self, start: date, end: date) -> Dict[str, Any]:
        """HRV-drop som korrelerer med dårlig session quality dagen etter."""
        default = DEFAULTS["hrv_drop_warning_pct"]
        drops: List[float] = []
        current = start + timedelta(days=14)
        while current <= end:
            baseline = self._ppap.get_hrv_baseline(current)
            delta = self._ppap.get_hrv_delta_pct(current)
            if baseline is None or delta is None:
                current += timedelta(days=1)
                continue
            next_day = current + timedelta(days=1)
            quality = self._hard_or_any_quality(next_day)
            if quality is not None and quality < 55 and float(delta) < 0:
                drops.append(float(delta))
            current += timedelta(days=1)

        return self._parameter_result(
            "hrv_drop_warning_pct",
            default,
            median(drops) if drops else None,
            len(drops),
            "median_hrv_delta_before_poor_session",
            drops,
        )

    def calibrate_rhr_rise(self, start: date, end: date) -> Dict[str, Any]:
        default = DEFAULTS["rhr_rise_warning_bpm"]
        rises: List[float] = []
        rows = (
            self.db.query(RestingHeartRate)
            .filter(
                and_(
                    RestingHeartRate.measurement_date >= start,
                    RestingHeartRate.measurement_date <= end,
                    RestingHeartRate.resting_heart_rate.isnot(None),
                )
            )
            .order_by(RestingHeartRate.measurement_date)
            .all()
        )
        if len(rows) < 20:
            return self._parameter_result(
                "rhr_rise_warning_bpm",
                default,
                None,
                len(rows),
                "insufficient_rhr_series",
                [],
            )
        values = [float(r.resting_heart_rate) for r in rows]
        baseline = sum(values[:14]) / 14
        for value in values[14:]:
            delta = value - baseline
            if delta > 0:
                rises.append(delta)
            baseline = baseline * 0.9 + value * 0.1
        personalized = median(rises) * 1.2 if rises else None
        return self._parameter_result(
            "rhr_rise_warning_bpm",
            default,
            personalized,
            len(rises),
            "rolling_baseline_positive_deltas",
            rises,
        )

    def calibrate_tsb_for_hard(self, start: date, end: date) -> Dict[str, Any]:
        default_min = DEFAULTS["tsb_hard_session_min"]
        default_max = DEFAULTS["tsb_hard_session_max"]
        good_tsb: List[float] = []
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity) or not activity.start_time:
                continue
            classification = self._classifier.classify_activity(activity)
            if classification.get("session_type") not in HARD_SESSION_TYPES:
                continue
            day = activity.start_time.date()
            tsb = self._ppap.get_tsb(day)
            quality = self._quality.evaluate(activity).get("quality_score")
            if tsb is not None and quality is not None and quality >= 70:
                good_tsb.append(float(tsb))

        if len(good_tsb) < MIN_SAMPLES_PERSONALIZE:
            return {
                "parameter": "tsb_hard_session_range",
                "default_value": [default_min, default_max],
                "personalized_value": None,
                "confidence": 0.0,
                "sample_count": len(good_tsb),
                "method": "insufficient_good_hard_sessions",
                "use_personalized": False,
            }

        lo = max(default_min - 5, min(good_tsb))
        hi = min(default_max + 5, max(good_tsb))
        # Use 20th–80th percentile approx via sorted slice
        ordered = sorted(good_tsb)
        lo = ordered[max(0, len(ordered) // 5)]
        hi = ordered[min(len(ordered) - 1, (4 * len(ordered)) // 5)]
        confidence = confidence_from_sample_count(len(good_tsb), min_samples=MIN_SAMPLES_PERSONALIZE)
        use = confidence >= 0.6 and self._stable(good_tsb)
        return {
            "parameter": "tsb_hard_session_range",
            "default_value": [default_min, default_max],
            "personalized_value": [round(lo, 1), round(hi, 1)] if use else None,
            "confidence": round(confidence, 2),
            "sample_count": len(good_tsb),
            "method": "percentile_tsb_on_good_hard_sessions",
            "use_personalized": use,
        }

    def calibrate_hard_spacing(self, start: date, end: date) -> Dict[str, Any]:
        default = DEFAULTS["hard_session_spacing_hours"]
        gaps: List[float] = []
        hard_days: List[date] = []
        current = start
        while current <= end:
            if self._day_has_hard(current):
                hard_days.append(current)
            current += timedelta(days=1)
        for i in range(1, len(hard_days)):
            hours = (hard_days[i] - hard_days[i - 1]).total_seconds() / 3600.0
            if 12 <= hours <= 120:
                gaps.append(hours)
        personalized = median(gaps) if gaps else None
        return self._parameter_result(
            "hard_session_spacing_hours",
            default,
            personalized,
            len(gaps),
            "median_gap_between_hard_days",
            gaps,
        )

    def calibrate_acwr_tolerance(self, start: date, end: date) -> Dict[str, Any]:
        default = DEFAULTS["acwr_caution"]
        good_acwr: List[float] = []
        current = start + timedelta(days=42)
        while current <= end:
            ctl = self._ppap.get_ctl(current)
            atl = self._ppap.get_atl(current)
            if ctl and atl and float(ctl) > 0:
                acwr = float(atl) / float(ctl)
                quality = self._hard_or_any_quality(current)
                if quality is not None and quality >= 70 and acwr > 0.8:
                    good_acwr.append(acwr)
            current += timedelta(days=3)
        personalized = (sorted(good_acwr)[int(len(good_acwr) * 0.9)] if len(good_acwr) >= 5 else None)
        return self._parameter_result(
            "acwr_caution",
            default,
            personalized,
            len(good_acwr),
            "p90_acwr_on_good_quality_days",
            good_acwr,
        )

    def calibrate_threshold_density(self, start: date, end: date) -> Dict[str, Any]:
        default = DEFAULTS["threshold_density_max_pct"]
        from .coaching_analysis_service import CoachingAnalysisService

        analysis = CoachingAnalysisService(self.db, self.storage).build_coaching_analysis(
            days=min(90, (end - start).days + 1),
            end_date=end,
        )
        zone2 = analysis.get("polarized_training", {}).get("percentages", {}).get("threshold")
        personalized = float(zone2) if zone2 is not None else None
        # Only personalize if athlete historically thrives with different density — keep conservative
        use = False
        return {
            "parameter": "threshold_density_max_pct",
            "default_value": default,
            "personalized_value": personalized if use else None,
            "confidence": 0.2 if personalized is not None else 0.0,
            "sample_count": analysis.get("polarized_training", {}).get("method_counts", {}).get("detailed_hr", 0),
            "method": "observed_zone2_pct_conservative_no_auto_personalize",
            "use_personalized": False,
            "observed_value": personalized,
        }

    def get_effective_value(self, parameter: str, calibration: Optional[Dict[str, Any]] = None) -> float:
        if calibration is None:
            calibration = self.calibrate_all()
        for item in calibration.get("parameters", []):
            if item.get("parameter") == parameter:
                if item.get("use_personalized") and item.get("personalized_value") is not None:
                    value = item["personalized_value"]
                    if isinstance(value, list):
                        return float(value[0])
                    return float(value)
                default = item.get("default_value", DEFAULTS.get(parameter))
                if isinstance(default, list):
                    return float(default[0])
                return float(default)
        return float(DEFAULTS.get(parameter, 0.0))

    def _parameter_result(
        self,
        name: str,
        default: float,
        personalized: Optional[float],
        sample_count: int,
        method: str,
        samples: List[float],
    ) -> Dict[str, Any]:
        confidence = confidence_from_sample_count(
            sample_count,
            min_samples=MIN_SAMPLES_PERSONALIZE // 2,
            target_samples=MIN_SAMPLES_PERSONALIZE * 2,
        )
        use = (
            personalized is not None
            and sample_count >= MIN_SAMPLES_PERSONALIZE
            and confidence >= 0.55
            and self._stable(samples)
        )
        return {
            "parameter": name,
            "default_value": default,
            "personalized_value": round(personalized, 2) if personalized is not None and use else None,
            "confidence": round(confidence, 2),
            "sample_count": sample_count,
            "method": method,
            "use_personalized": use,
        }

    @staticmethod
    def _stable(samples: List[float]) -> bool:
        if len(samples) < 5:
            return False
        mean_v = sum(samples) / len(samples)
        if abs(mean_v) < 1e-6:
            return pstdev(samples) < 1.0
        cv = pstdev(samples) / abs(mean_v)
        return cv <= MAX_CV_FOR_PERSONALIZE

    def _day_has_hard(self, day: date) -> bool:
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(func.date(Activity.start_time) == day)
            .all()
        )
        for activity in activities:
            if not is_running_activity(activity):
                continue
            if self._classifier.classify_activity(activity, end_date=day).get("session_type") in HARD_SESSION_TYPES:
                return True
        return False

    def _hard_or_any_quality(self, day: date) -> Optional[float]:
        activities = (
            self.db.query(Activity)
            .options(joinedload(Activity.activity_type))
            .filter(func.date(Activity.start_time) == day)
            .all()
        )
        scores = []
        for activity in activities:
            if not is_running_activity(activity):
                continue
            q = self._quality.evaluate(activity).get("quality_score")
            if q is not None:
                scores.append(float(q))
        return sum(scores) / len(scores) if scores else None
