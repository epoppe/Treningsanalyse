from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database.models import HRV, RestingHeartRate, Sleep
from ..database.models.activity import Activity, AnalyticsSnapshot
from ..database.models.lactate_threshold_history import LactateThresholdHistory
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .training_stress_service import TrainingStressService


class CoachingAnalysisService:
    """Evidence-informed training coaching metrics from local Garmin/training data.

    The calculations deliberately expose both measured data and heuristics. LT1 is
    usually not measured by Garmin, so it is estimated from LT2 when no direct
    marker exists.
    """

    SNAPSHOT_KEY = "training_coaching"
    FITNESS_TAU_DAYS = 42
    FATIGUE_TAU_DAYS = 7
    HRV_BASELINE_DAYS = 60

    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self.tss_service = TrainingStressService(db)

    def build_coaching_analysis(
        self,
        days: int = 90,
        *,
        end_date: Optional[date] = None,
        include_treadmill: bool = False,
        persist_snapshot: bool = False,
    ) -> Dict[str, Any]:
        end_date = end_date or date.today()
        start_date = end_date - timedelta(days=days - 1)
        warmup_start = start_date - timedelta(days=self.FITNESS_TAU_DAYS * 2)

        activities = self._activities(warmup_start, end_date, include_treadmill=include_treadmill)
        running_activities = [
            activity
            for activity in activities
            if is_running_activity(activity, include_treadmill=include_treadmill)
        ]
        daily_load = self._daily_training_load(activities, warmup_start, end_date)
        banister = self._banister_model(daily_load, start_date, end_date)
        thresholds = self._threshold_estimates(running_activities, end_date)
        polarized = self._polarized_distribution(
            running_activities,
            start_date,
            end_date,
            thresholds,
            include_treadmill=include_treadmill,
        )
        hrv_guidance = self._hrv_guidance(end_date)
        diagnostics = self._diagnostics(banister, polarized, thresholds, hrv_guidance)

        payload = {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days,
                "include_treadmill": include_treadmill,
            },
            "banister": banister,
            "polarized_training": polarized,
            "thresholds": thresholds,
            "hrv_guidance": hrv_guidance,
            "diagnostics": diagnostics,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "model_notes": [
                "Fitness/fatigue uses 42/7 day impulse-response EMA over daily training load.",
                "Intensity distribution is time in LT1/LT2 buckets from detailed HR samples when available, otherwise average HR fallback.",
                "LT2 uses latest lactate threshold HR/speed from Garmin/history. LT1 is estimated heuristically when not directly measured.",
                "HRV guidance compares recent RMSSD, sleep and resting HR with personal baselines.",
            ],
        }
        if persist_snapshot:
            self._persist_snapshot(payload)
        return payload

    def get_snapshot_payload(self) -> Optional[Dict[str, Any]]:
        snapshot = self.db.query(AnalyticsSnapshot).filter_by(metric_key=self.SNAPSHOT_KEY).first()
        return snapshot.payload if snapshot else None

    def _persist_snapshot(self, payload: Dict[str, Any]) -> None:
        snapshot = self.db.query(AnalyticsSnapshot).filter_by(metric_key=self.SNAPSHOT_KEY).first()
        if snapshot is None:
            snapshot = AnalyticsSnapshot(metric_key=self.SNAPSHOT_KEY)
            self.db.add(snapshot)
        snapshot.payload = payload
        snapshot.calculated_at = datetime.now(timezone.utc)
        snapshot.data_quality_score = payload.get("diagnostics", {}).get("data_quality_score")
        snapshot.model_quality = payload.get("diagnostics", {}).get("model_quality")
        self.db.commit()

    def _activities(
        self,
        start_date: date,
        end_date: date,
        *,
        include_treadmill: bool,
    ) -> List[Activity]:
        query = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start_date,
                    func.date(Activity.start_time) <= end_date,
                )
            )
            .order_by(Activity.start_time.asc())
        )
        activities = query.all()
        if include_treadmill:
            return activities
        return [
            activity
            for activity in activities
            if not (
                activity.activity_type
                and activity.activity_type.type_key in {"treadmill_running", "indoor_running"}
            )
        ]

    def _activity_load(self, activity: Activity) -> float:
        if activity.training_stress_score and activity.training_stress_score > 0:
            return float(activity.training_stress_score)
        if activity.epoc and activity.epoc > 0:
            return float(activity.epoc)
        return float(self.tss_service.calculate_tss_for_activity(activity) or 0.0)

    def _daily_training_load(
        self,
        activities: List[Activity],
        start_date: date,
        end_date: date,
    ) -> Dict[date, float]:
        daily = defaultdict(float)
        for activity in activities:
            if not activity.start_time:
                continue
            load = self._activity_load(activity)
            if load > 0:
                daily[activity.start_time.date()] += load

        current = start_date
        while current <= end_date:
            daily.setdefault(current, 0.0)
            current += timedelta(days=1)
        return dict(daily)

    def _banister_model(
        self,
        daily_load: Dict[date, float],
        report_start: date,
        end_date: date,
    ) -> Dict[str, Any]:
        fitness = 0.0
        fatigue = 0.0
        fitness_alpha = 1.0 - pow(2.718281828, -1.0 / self.FITNESS_TAU_DAYS)
        fatigue_alpha = 1.0 - pow(2.718281828, -1.0 / self.FATIGUE_TAU_DAYS)
        rows = []

        for day in sorted(daily_load):
            load = float(daily_load[day])
            fitness = fitness + fitness_alpha * (load - fitness)
            fatigue = fatigue + fatigue_alpha * (load - fatigue)
            if day >= report_start:
                rows.append(
                    {
                        "date": day.isoformat(),
                        "load": round(load, 1),
                        "fitness": round(fitness, 1),
                        "fatigue": round(fatigue, 1),
                        "performance": round(fitness - fatigue, 1),
                    }
                )

        latest = rows[-1] if rows else {"fitness": 0, "fatigue": 0, "performance": 0, "load": 0}
        previous_7_load = sum(v for d, v in daily_load.items() if end_date - timedelta(days=6) <= d <= end_date)
        previous_28_load = sum(v for d, v in daily_load.items() if end_date - timedelta(days=27) <= d <= end_date)
        avg_28 = previous_28_load / 4 if previous_28_load else 0
        load_ratio = previous_7_load / avg_28 if avg_28 > 0 else None

        return {
            "model": "banister_fitness_fatigue",
            "fitness_tau_days": self.FITNESS_TAU_DAYS,
            "fatigue_tau_days": self.FATIGUE_TAU_DAYS,
            "summary": {
                "fitness": latest["fitness"],
                "fatigue": latest["fatigue"],
                "performance": latest["performance"],
                "last_7_days_load": round(previous_7_load, 1),
                "previous_28_days_weekly_avg_load": round(avg_28, 1),
                "load_ratio_7d_to_28d_week": round(load_ratio, 2) if load_ratio is not None else None,
                "status": self._banister_status(float(latest["performance"]), load_ratio),
            },
            "daily": rows,
        }

    def _banister_status(self, performance: float, load_ratio: Optional[float]) -> str:
        if load_ratio is not None and load_ratio > 1.5:
            return "rapid_load_increase"
        if performance < -20:
            return "high_fatigue"
        if -20 <= performance <= 10:
            return "productive_load"
        if performance > 20:
            return "fresh_or_tapered"
        return "neutral"

    def _latest_threshold_history(self, end_date: date) -> Optional[LactateThresholdHistory]:
        return (
            self.db.query(LactateThresholdHistory)
            .filter(func.date(LactateThresholdHistory.observed_at) <= end_date)
            .order_by(LactateThresholdHistory.observed_at.desc())
            .first()
        )

    def _threshold_estimates(
        self,
        running_activities: List[Activity],
        end_date: date,
    ) -> Dict[str, Any]:
        history = self._latest_threshold_history(end_date)
        lt2_hr = history.lactate_threshold_heart_rate if history else None
        lt2_speed = history.lactate_threshold_speed if history else None
        if lt2_hr is None:
            hr_values = [
                activity.lactate_threshold_heart_rate
                for activity in running_activities
                if activity.lactate_threshold_heart_rate
            ]
            lt2_hr = hr_values[-1] if hr_values else None
        if lt2_speed is None:
            speed_values = [
                activity.lactate_threshold_speed
                for activity in running_activities
                if activity.lactate_threshold_speed
            ]
            lt2_speed = speed_values[-1] if speed_values else None

        lt1_hr = lt2_hr * 0.85 if lt2_hr else None
        lt1_speed = lt2_speed * 0.82 if lt2_speed else None
        drift_samples = [
            activity.hr_drift_pct
            for activity in running_activities[-20:]
            if activity.hr_drift_pct is not None
        ]
        decoupling_samples = [
            activity.decoupling_percent
            for activity in running_activities[-20:]
            if activity.decoupling_percent is not None
        ]
        pace_hr_ratio = self._pace_hr_ratio(running_activities[-30:], lt1_hr)

        return {
            "lt1": {
                "heart_rate_bpm": round(lt1_hr, 0) if lt1_hr else None,
                "speed_mps": round(lt1_speed, 3) if lt1_speed else None,
                "pace_sec_per_km": round(1000 / lt1_speed, 1) if lt1_speed and lt1_speed > 0 else None,
                "source": "estimated_from_lt2",
            },
            "lt2": {
                "heart_rate_bpm": round(lt2_hr, 0) if lt2_hr else None,
                "speed_mps": round(lt2_speed, 3) if lt2_speed else None,
                "pace_sec_per_km": round(1000 / lt2_speed, 1) if lt2_speed and lt2_speed > 0 else None,
                "source": "garmin_lactate_threshold" if history else "activity_lactate_threshold_or_missing",
                "observed_at": history.observed_at.isoformat() if history else None,
            },
            "drift": {
                "recent_median_hr_drift_pct": self._median(drift_samples),
                "recent_median_decoupling_pct": self._median(decoupling_samples),
                "sample_count": len(drift_samples) + len(decoupling_samples),
            },
            "pace_heart_rate": pace_hr_ratio,
        }

    def _pace_hr_ratio(
        self,
        activities: List[Activity],
        lt1_hr: Optional[float],
    ) -> Dict[str, Any]:
        candidates = []
        for activity in activities:
            if not activity.average_speed or not activity.average_heart_rate:
                continue
            if lt1_hr and activity.average_heart_rate > lt1_hr:
                continue
            candidates.append(activity.average_speed / activity.average_heart_rate)
        return {
            "recent_easy_speed_per_bpm_mps": round(sum(candidates) / len(candidates), 5) if candidates else None,
            "sample_count": len(candidates),
            "interpretation": "higher_is_better_for_running_economy_at_easy_intensity",
        }

    def _polarized_distribution(
        self,
        running_activities: List[Activity],
        start_date: date,
        end_date: date,
        thresholds: Dict[str, Any],
        *,
        include_treadmill: bool,
    ) -> Dict[str, Any]:
        lt1_hr = thresholds["lt1"].get("heart_rate_bpm")
        lt2_hr = thresholds["lt2"].get("heart_rate_bpm")
        buckets = {"low": 0.0, "threshold": 0.0, "high": 0.0, "unknown": 0.0}
        method_counts = {"detailed_hr": 0, "average_hr": 0, "unknown": 0}
        interval_days = set()

        for activity in running_activities:
            if not activity.start_time or not (start_date <= activity.start_time.date() <= end_date):
                continue
            act_buckets, method = self._activity_intensity_buckets(activity, lt1_hr, lt2_hr)
            for key, value in act_buckets.items():
                buckets[key] += value
            method_counts[method] += 1
            if act_buckets.get("high", 0) >= 10 * 60:
                interval_days.add(activity.start_time.date().isoformat())

        total_known = buckets["low"] + buckets["threshold"] + buckets["high"]
        percentages = {
            key: round((buckets[key] / total_known) * 100, 1) if total_known > 0 else None
            for key in ["low", "threshold", "high"]
        }
        flags = []
        if percentages["low"] is not None and percentages["low"] < 75:
            flags.append("too_little_easy_volume")
        if percentages["threshold"] is not None and percentages["threshold"] > 15:
            flags.append("too_much_threshold_density")
        if len(interval_days) > 2 and (end_date - start_date).days <= 13:
            flags.append("high_intensity_too_frequent")

        return {
            "model": "seiler_80_20_three_zone",
            "thresholds_used": {
                "lt1_hr_bpm": lt1_hr,
                "lt2_hr_bpm": lt2_hr,
            },
            "seconds": {key: round(value, 1) for key, value in buckets.items()},
            "percentages": percentages,
            "method_counts": method_counts,
            "high_intensity_days": sorted(interval_days),
            "flags": flags,
            "status": "polarized_ok" if not flags and total_known > 0 else "needs_attention",
            "include_treadmill": include_treadmill,
        }

    def _activity_intensity_buckets(
        self,
        activity: Activity,
        lt1_hr: Optional[float],
        lt2_hr: Optional[float],
    ) -> Tuple[Dict[str, float], str]:
        buckets = {"low": 0.0, "threshold": 0.0, "high": 0.0, "unknown": 0.0}
        if not lt1_hr or not lt2_hr:
            buckets["unknown"] = float(activity.duration or 0)
            return buckets, "unknown"

        details = self._activity_details(activity)
        if details is not None and not details.empty and "heart_rate" in details.columns:
            df = details.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df["heart_rate"] = pd.to_numeric(df["heart_rate"], errors="coerce")
            df = df.dropna(subset=["timestamp", "heart_rate"]).sort_values("timestamp")
            if len(df) >= 2:
                elapsed = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()
                dt = elapsed.diff().shift(-1)
                fallback = dt[(dt > 0) & (dt <= 10)].median()
                if pd.isna(fallback):
                    fallback = 1.0
                df["dt_s"] = dt.fillna(fallback).clip(lower=0.1, upper=10)
                for _, row in df.iterrows():
                    buckets[self._intensity_bucket(float(row["heart_rate"]), lt1_hr, lt2_hr)] += float(row["dt_s"])
                return buckets, "detailed_hr"

        if activity.average_heart_rate and activity.duration:
            buckets[self._intensity_bucket(float(activity.average_heart_rate), lt1_hr, lt2_hr)] = float(activity.duration)
            return buckets, "average_hr"

        buckets["unknown"] = float(activity.duration or 0)
        return buckets, "unknown"

    def _activity_details(self, activity: Activity) -> Optional[pd.DataFrame]:
        if self.storage is None:
            return None
        try:
            return self.storage.get_activity_details(int(activity.activity_id))
        except Exception:
            return None

    def _intensity_bucket(self, heart_rate: float, lt1_hr: float, lt2_hr: float) -> str:
        if heart_rate <= lt1_hr:
            return "low"
        if heart_rate <= lt2_hr:
            return "threshold"
        return "high"

    def _hrv_guidance(self, target_date: date) -> Dict[str, Any]:
        baseline_start = target_date - timedelta(days=self.HRV_BASELINE_DAYS)
        recent_start = target_date - timedelta(days=6)
        hrv_rows = (
            self.db.query(HRV)
            .filter(and_(HRV.measurement_date >= baseline_start, HRV.measurement_date <= target_date))
            .order_by(HRV.measurement_date.asc())
            .all()
        )
        sleep_rows = (
            self.db.query(Sleep)
            .filter(and_(Sleep.sleep_date >= recent_start, Sleep.sleep_date <= target_date))
            .order_by(Sleep.sleep_date.asc())
            .all()
        )
        rhr_rows = (
            self.db.query(RestingHeartRate)
            .filter(and_(RestingHeartRate.measurement_date >= baseline_start, RestingHeartRate.measurement_date <= target_date))
            .order_by(RestingHeartRate.measurement_date.asc())
            .all()
        )

        baseline_hrv = [row.rmssd for row in hrv_rows if row.rmssd and row.measurement_date < recent_start]
        recent_hrv = [row.rmssd for row in hrv_rows if row.rmssd and row.measurement_date >= recent_start]
        sleep_scores = [
            (row.overall_score if row.overall_score is not None else row.sleep_score)
            for row in sleep_rows
            if (row.overall_score if row.overall_score is not None else row.sleep_score) is not None
        ]
        baseline_rhr = [
            row.resting_heart_rate
            for row in rhr_rows
            if row.resting_heart_rate and row.measurement_date < recent_start
        ]
        recent_rhr = [
            row.resting_heart_rate
            for row in rhr_rows
            if row.resting_heart_rate and row.measurement_date >= recent_start
        ]

        hrv_baseline = self._mean(baseline_hrv)
        hrv_recent = self._mean(recent_hrv)
        hrv_delta_pct = (
            ((hrv_recent - hrv_baseline) / hrv_baseline) * 100
            if hrv_recent is not None and hrv_baseline and hrv_baseline > 0
            else None
        )
        rhr_baseline = self._mean(baseline_rhr)
        rhr_recent = self._mean(recent_rhr)
        rhr_delta = rhr_recent - rhr_baseline if rhr_recent is not None and rhr_baseline is not None else None
        avg_sleep = self._mean(sleep_scores)

        flags = []
        if hrv_delta_pct is not None and hrv_delta_pct < -8:
            flags.append("hrv_below_baseline")
        if rhr_delta is not None and rhr_delta > 4:
            flags.append("resting_hr_elevated")
        if avg_sleep is not None and avg_sleep < 65:
            flags.append("sleep_low")

        recommendation = "normal_training"
        if len(flags) >= 2:
            recommendation = "reduce_intensity_or_volume"
        elif flags:
            recommendation = "keep_easy_or_moderate"

        return {
            "baseline_days": self.HRV_BASELINE_DAYS,
            "recent_days": 7,
            "rmssd_baseline": round(hrv_baseline, 1) if hrv_baseline is not None else None,
            "rmssd_recent": round(hrv_recent, 1) if hrv_recent is not None else None,
            "rmssd_delta_pct": round(hrv_delta_pct, 1) if hrv_delta_pct is not None else None,
            "resting_hr_baseline": round(rhr_baseline, 1) if rhr_baseline is not None else None,
            "resting_hr_recent": round(rhr_recent, 1) if rhr_recent is not None else None,
            "resting_hr_delta_bpm": round(rhr_delta, 1) if rhr_delta is not None else None,
            "sleep_score_recent": round(avg_sleep, 1) if avg_sleep is not None else None,
            "flags": flags,
            "recommendation": recommendation,
            "data_points": {
                "hrv": len(hrv_rows),
                "sleep": len(sleep_rows),
                "resting_hr": len(rhr_rows),
            },
        }

    def _diagnostics(
        self,
        banister: Dict[str, Any],
        polarized: Dict[str, Any],
        thresholds: Dict[str, Any],
        hrv_guidance: Dict[str, Any],
    ) -> Dict[str, Any]:
        flags = []
        flags.extend(polarized.get("flags", []))
        flags.extend(hrv_guidance.get("flags", []))
        banister_status = banister.get("summary", {}).get("status")
        if banister_status in {"rapid_load_increase", "high_fatigue"}:
            flags.append(banister_status)
        if thresholds.get("lt2", {}).get("heart_rate_bpm") is None:
            flags.append("missing_lt2_heart_rate")

        quality = 100
        if polarized.get("method_counts", {}).get("detailed_hr", 0) == 0:
            quality -= 20
        if thresholds.get("lt2", {}).get("heart_rate_bpm") is None:
            quality -= 25
        if hrv_guidance.get("data_points", {}).get("hrv", 0) < 14:
            quality -= 20
        quality = max(0, min(100, quality))

        return {
            "flags": sorted(set(flags)),
            "data_quality_score": quality,
            "model_quality": "good" if quality >= 75 else "limited" if quality >= 50 else "low",
        }

    def _median(self, values: List[float]) -> Optional[float]:
        clean = sorted(float(v) for v in values if v is not None)
        if not clean:
            return None
        midpoint = len(clean) // 2
        if len(clean) % 2:
            return round(clean[midpoint], 2)
        return round((clean[midpoint - 1] + clean[midpoint]) / 2, 2)

    def _mean(self, values: List[float]) -> Optional[float]:
        clean = [float(v) for v in values if v is not None]
        if not clean:
            return None
        return sum(clean) / len(clean)
