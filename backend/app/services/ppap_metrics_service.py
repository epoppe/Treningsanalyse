from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import median, pstdev
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database.models import HRV, RestingHeartRate, Sleep
from ..database.models.activity import Activity
from ..utils.activity_filters import is_running_activity
from .coaching_analysis_service import CoachingAnalysisService
from .performance_metrics_service import PerformanceMetricsService
from .training_readiness_service import TrainingReadinessService
from .training_stress_service import TrainingStressService

# MCP-nøkler → varighet (sekunder) for duration curve (power og speed)
DURATION_CURVE_METRICS: Dict[str, Tuple[str, int]] = {
    "running.power_30s": ("power", 30),
    "running.power_1m": ("power", 60),
    "running.power_3m": ("power", 180),
    "running.power_5m": ("power", 300),
    "running.power_10m": ("power", 600),
    "running.power_20m": ("power", 1200),
    "running.power_40m": ("power", 2400),
    "running.power_60m": ("power", 3600),
    "running.speed_30s": ("speed", 30),
    "running.speed_1m": ("speed", 60),
    "running.speed_3m": ("speed", 180),
    "running.speed_5m": ("speed", 300),
    "running.speed_10m": ("speed", 600),
    "running.speed_20m": ("speed", 1200),
    "running.speed_40m": ("speed", 2400),
    "running.speed_60m": ("speed", 3600),
}

COACHING_ZONE_METRICS = {
    "coaching.zone1_pct": "low",
    "coaching.zone2_pct": "threshold",
    "coaching.zone3_pct": "high",
}

READINESS_COMPONENT_METRICS = {
    "readiness.total_score": "total_score",
    "readiness.sleep_component": "sleep_score",
    "readiness.hrv_component": "hrv_score",
    "readiness.form_component": "form_score",
}

TRAINING_CLASS_LABELS = (
    "recovery",
    "easy",
    "aerobic",
    "tempo",
    "threshold",
    "vo2",
    "anaerobic",
    "race",
)

ROLLING_CURVE_LOOKBACK_DAYS = 365

SLEEP_DEBT_TARGET_SECONDS = 8 * 3600


class PpapMetricsService:
    """PPAP-aligned metrics (CTL/ATL/TSB, rollups) shared by MCP and REST."""

    CTL_TAU_DAYS = 42
    ATL_TAU_DAYS = 7
    HRV_BASELINE_DAYS = 28
    LOAD_WARMUP_DAYS = 400
    POLARIZED_WINDOW_DAYS = 28

    def __init__(self, db: Session, storage: Optional[Any] = None):
        self.db = db
        self.storage = storage
        self._tss_service = TrainingStressService(db)
        self._load_by_date: Optional[Dict[str, Dict[str, float]]] = None
        self._load_series_end: Optional[date] = None
        self._duration_curve_cache: Optional[Dict[str, Any]] = None
        self._polarized_cache: Dict[Tuple[date, int], Dict[str, Any]] = {}
        self._readiness_cache: Dict[date, Dict[str, Any]] = {}

    def ensure_load_series(self, end_date: date) -> None:
        if self._load_by_date is not None and self._load_series_end == end_date:
            return

        start_date = end_date - timedelta(days=self.LOAD_WARMUP_DAYS)
        daily_tss: Dict[str, float] = {}
        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start_date,
                    func.date(Activity.start_time) <= end_date,
                )
            )
            .order_by(Activity.start_time)
            .all()
        )
        for activity in activities:
            try:
                tss = float(self._tss_service.calculate_tss_for_activity(activity))
            except Exception:
                continue
            if tss <= 0 or activity.start_time is None:
                continue
            day_key = activity.start_time.date().isoformat()
            daily_tss[day_key] = daily_tss.get(day_key, 0.0) + tss

        ctl = 0.0
        atl = 0.0
        initialized = False
        series: Dict[str, Dict[str, float]] = {}
        current = start_date
        while current <= end_date:
            day_key = current.isoformat()
            tss_today = daily_tss.get(day_key, 0.0)
            if not initialized and tss_today > 0:
                ctl = tss_today
                atl = tss_today
                initialized = True
            elif initialized:
                ctl = ctl + (tss_today - ctl) / self.CTL_TAU_DAYS
                atl = atl + (tss_today - atl) / self.ATL_TAU_DAYS
            series[day_key] = {
                "tss": round(tss_today, 1),
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(ctl - atl, 1),
            }
            current += timedelta(days=1)

        self._load_by_date = series
        self._load_series_end = end_date

    def get_load_metrics(self, day: date) -> Dict[str, Optional[float]]:
        self.ensure_load_series(day)
        payload = (self._load_by_date or {}).get(day.isoformat())
        if payload is None:
            return {"tss": None, "ctl": None, "atl": None, "tsb": None}
        return payload

    def get_ctl(self, day: date) -> Optional[float]:
        return self.get_load_metrics(day).get("ctl")

    def get_atl(self, day: date) -> Optional[float]:
        return self.get_load_metrics(day).get("atl")

    def get_tsb(self, day: date) -> Optional[float]:
        return self.get_load_metrics(day).get("tsb")

    def get_ef_rolling(self, day: date, window_days: int) -> Optional[float]:
        start = day - timedelta(days=window_days - 1)
        rows = (
            self.db.query(Activity.avg_efficiency_factor)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= day,
                    Activity.avg_efficiency_factor.isnot(None),
                )
            )
            .all()
        )
        values = [float(row.avg_efficiency_factor) for row in rows if row.avg_efficiency_factor is not None]
        if not values:
            return None
        return round(median(values), 6)

    def get_hrv_baseline(self, day: date) -> Optional[float]:
        end = day - timedelta(days=1)
        start = end - timedelta(days=self.HRV_BASELINE_DAYS - 1)
        if end < start:
            return None
        rows = (
            self.db.query(HRV.rmssd)
            .filter(
                and_(
                    HRV.measurement_date >= start,
                    HRV.measurement_date <= end,
                    HRV.rmssd.isnot(None),
                )
            )
            .all()
        )
        values = [float(row.rmssd) for row in rows if row.rmssd is not None]
        if not values:
            return None
        return round(median(values), 1)

    def get_hrv_delta_pct(self, day: date) -> Optional[float]:
        today_row = (
            self.db.query(HRV.rmssd)
            .filter(and_(HRV.measurement_date == day, HRV.rmssd.isnot(None)))
            .first()
        )
        if today_row is None or today_row.rmssd is None:
            return None
        baseline = self.get_hrv_baseline(day)
        if baseline is None or baseline <= 0:
            return None
        return round((float(today_row.rmssd) - baseline) / baseline * 100.0, 2)

    def get_rhr_rolling(self, day: date, window_days: int) -> Optional[float]:
        start = day - timedelta(days=window_days - 1)
        rows = (
            self.db.query(RestingHeartRate.resting_heart_rate)
            .filter(
                and_(
                    RestingHeartRate.measurement_date >= start,
                    RestingHeartRate.measurement_date <= day,
                    RestingHeartRate.resting_heart_rate.isnot(None),
                )
            )
            .all()
        )
        values = [
            float(row.resting_heart_rate)
            for row in rows
            if row.resting_heart_rate is not None
        ]
        if not values:
            return None
        return round(sum(values) / len(values), 1)

    def _duration_curve_payload(self) -> Dict[str, Any]:
        if self._duration_curve_cache is not None:
            return self._duration_curve_cache
        if self.storage is None:
            self._duration_curve_cache = {}
            return self._duration_curve_cache
        service = PerformanceMetricsService(self.db, self.storage)
        payload = service.get_snapshot_payload("duration_curve")
        if not payload:
            payload = service.recalculate_performance_snapshots().get("duration_curve", {})
        self._duration_curve_cache = payload or {}
        return self._duration_curve_cache

    def get_duration_curve_value(self, metric_key: str, _day: date) -> Optional[float]:
        spec = DURATION_CURVE_METRICS.get(metric_key)
        if spec is None:
            return None
        metric_type, duration_s = spec
        curves = self._duration_curve_payload().get("all_time", {}).get("curves", {})
        entries = curves.get(metric_type, [])
        for entry in entries:
            if entry.get("duration_seconds") == duration_s:
                if metric_type == "power":
                    return entry.get("power_watts")
                return entry.get("speed_mps")
        return None

    def get_coaching_zone_pct(self, day: date, zone_key: str) -> Optional[float]:
        bucket = COACHING_ZONE_METRICS.get(zone_key)
        if bucket is None:
            return None
        cache_key = (day, self.POLARIZED_WINDOW_DAYS)
        if cache_key not in self._polarized_cache:
            service = CoachingAnalysisService(self.db, self.storage)
            self._polarized_cache[cache_key] = service.build_coaching_analysis(
                days=self.POLARIZED_WINDOW_DAYS,
                end_date=day,
                include_treadmill=False,
            )
        percentages = self._polarized_cache[cache_key].get("polarized_training", {}).get("percentages", {})
        return percentages.get(bucket)

    def get_readiness_component(self, day: date, metric_key: str) -> Optional[float]:
        field = READINESS_COMPONENT_METRICS.get(metric_key)
        if field is None:
            return None
        if day not in self._readiness_cache:
            service = TrainingReadinessService(self.db)
            try:
                self._readiness_cache[day] = service.calculate_training_readiness(day)
            finally:
                service.close()
        payload = self._readiness_cache[day]
        if field == "total_score":
            value = payload.get("total_score")
        else:
            value = payload.get("components", {}).get(field)
        return round(float(value), 1) if value is not None else None

    def get_predicted_recovery_hours(self, day: date) -> Optional[float]:
        total = self.get_readiness_component(day, "readiness.total_score")
        tsb = self.get_tsb(day)
        hrv_delta = self.get_hrv_delta_pct(day)
        hours = 18.0
        if total is not None:
            if total < 35:
                hours += 30.0
            elif total < 50:
                hours += 18.0
            elif total < 65:
                hours += 8.0
            elif total >= 80:
                hours -= 6.0
        if tsb is not None:
            if tsb < -25:
                hours += 24.0
            elif tsb < -12:
                hours += 12.0
            elif tsb > 10:
                hours -= 4.0
        if hrv_delta is not None and float(hrv_delta) < -15:
            hours += 10.0
        return round(max(6.0, min(120.0, hours)), 1)

    def get_rolling_duration_curve_value(
        self,
        metric_key: str,
        day: date,
        *,
        lookback_days: int = ROLLING_CURVE_LOOKBACK_DAYS,
    ) -> Optional[float]:
        base_key = metric_key[:-5] if metric_key.endswith("_hist") else metric_key
        if base_key not in DURATION_CURVE_METRICS or self.storage is None:
            return None
        metric_type, duration_s = DURATION_CURVE_METRICS[base_key]
        service = PerformanceMetricsService(self.db, self.storage)
        curve = service.build_duration_curve(
            days=lookback_days,
            include_treadmill=False,
            end_date=day,
        )
        for point in curve.get("curves", {}).get(metric_type, []):
            if int(point.get("duration_seconds", 0)) != duration_s:
                continue
            if metric_type == "speed":
                value = point.get("speed_mps")
            else:
                value = point.get("power_watts")
            return round(float(value), 4) if value is not None else None
        return None

    def duration_curve_snapshot(
        self,
        *,
        scope: str = "all_time",
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        if self.storage is None:
            return {"status": "missing_storage", "scope": scope}
        service = PerformanceMetricsService(self.db, self.storage)
        scope_days = {"all_time": None, "last_90_days": 90, "last_365_days": 365}
        days = scope_days.get(scope)
        payload = service.get_snapshot_payload("duration_curve")
        if payload and not include_treadmill and scope in payload:
            scoped = payload.get(scope) or payload.get("all_time")
            return {
                "status": "ok",
                "scope": scope,
                "include_treadmill": include_treadmill,
                "calculated_at": payload.get("calculated_at"),
                **scoped,
            }
        curve = service.build_duration_curve(days=days, include_treadmill=include_treadmill)
        return {
            "status": "ok",
            "scope": scope,
            "include_treadmill": include_treadmill,
            **curve,
        }

    def duration_curve_year_comparison(
        self,
        *,
        years: int = 3,
        metric: str = "speed",
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        if self.storage is None:
            return {"status": "missing_storage", "metric": metric, "years": []}
        service = PerformanceMetricsService(self.db, self.storage)
        series_raw = service.build_duration_curve_year_comparison(
            years=years,
            include_treadmill=include_treadmill,
        )
        series = []
        for entry in series_raw:
            curves = entry.get("curves", {})
            series.append(
                {
                    "year": entry.get("year"),
                    "points": curves.get(metric, []),
                    "effort_count": entry.get("effort_count", 0),
                }
            )
        return {
            "status": "ok",
            "metric": metric,
            "years": series,
            "include_treadmill": include_treadmill,
        }

    def critical_speed_pace_by_year(
        self,
        *,
        years: int = 3,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        if self.storage is None:
            return {"status": "missing_storage"}
        service = PerformanceMetricsService(self.db, self.storage)
        return service.build_critical_speed_pace_by_year(
            years=years,
            include_treadmill=include_treadmill,
        )

    def hr_to_training_class(
        self,
        hr: float,
        *,
        lt1: Optional[float],
        lt2: Optional[float],
        hr_max: Optional[float],
    ) -> int:
        if lt1 and lt2 and lt1 > 0 and lt2 > lt1:
            if hr < lt1 * 0.88:
                return 1
            if hr < lt1:
                return 2
            if hr < (lt1 + lt2) / 2:
                return 3
            if hr < lt2 * 0.97:
                return 4
            if hr < lt2:
                return 5
            if hr < lt2 * 1.04:
                return 6
            if hr < lt2 * 1.10:
                return 7
            return 8
        ceiling = hr_max or 190.0
        ratio = hr / ceiling if ceiling > 0 else 0.0
        if ratio < 0.60:
            return 1
        if ratio < 0.68:
            return 2
        if ratio < 0.75:
            return 3
        if ratio < 0.82:
            return 4
        if ratio < 0.88:
            return 5
        if ratio < 0.93:
            return 6
        if ratio < 0.97:
            return 7
        return 8

    def get_training_class_percentages(
        self,
        day: date,
        window_days: int = 28,
    ) -> Dict[str, Optional[float]]:
        start = day - timedelta(days=window_days - 1)
        if not hasattr(self, "_class_pct_cache"):
            self._class_pct_cache = {}
        cache_key = (day, window_days)
        if cache_key in self._class_pct_cache:
            return self._class_pct_cache[cache_key]

        coaching = CoachingAnalysisService(self.db, self.storage)
        analysis = coaching.build_coaching_analysis(
            days=max(window_days, 30),
            end_date=day,
            include_treadmill=False,
        )
        thresholds = analysis.get("thresholds", {})
        lt1 = thresholds.get("lt1", {}).get("heart_rate_bpm")
        lt2 = thresholds.get("lt2", {}).get("heart_rate_bpm")
        hr_max = float(lt2) * 1.08 if lt2 else None

        activities = (
            self.db.query(Activity)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= day,
                    Activity.average_heart_rate.isnot(None),
                )
            )
            .all()
        )
        seconds = {index: 0.0 for index in range(1, 9)}
        for activity in activities:
            if not is_running_activity(activity) or not activity.average_heart_rate:
                continue
            duration = float(activity.duration or 0)
            if duration <= 0:
                continue
            zone = self.hr_to_training_class(
                float(activity.average_heart_rate),
                lt1=lt1,
                lt2=lt2,
                hr_max=hr_max,
            )
            seconds[zone] += duration

        total = sum(seconds.values())
        result: Dict[str, Optional[float]] = {}
        for index in range(1, 9):
            key = f"training.class_{index}_pct"
            result[key] = None if total <= 0 else round(seconds[index] / total * 100.0, 1)
        self._class_pct_cache[cache_key] = result
        return result

    def get_training_class_pct(self, day: date, metric_key: str) -> Optional[float]:
        return self.get_training_class_percentages(day).get(metric_key)

    def get_training_class_for_activity(self, activity: Activity, day: date) -> Optional[int]:
        if not activity.average_heart_rate:
            return None
        coaching = CoachingAnalysisService(self.db, self.storage)
        thresholds = coaching.build_coaching_analysis(days=90, end_date=day).get("thresholds", {})
        lt1 = thresholds.get("lt1", {}).get("heart_rate_bpm")
        lt2 = thresholds.get("lt2", {}).get("heart_rate_bpm")
        hr_max = float(lt2) * 1.08 if lt2 else None
        return self.hr_to_training_class(
            float(activity.average_heart_rate),
            lt1=lt1,
            lt2=lt2,
            hr_max=hr_max,
        )

    def extended_performance_driver(self, day: date) -> Tuple[Optional[str], Optional[float], Dict[str, float]]:
        coaching = CoachingAnalysisService(self.db, self.storage)
        analysis = coaching.build_coaching_analysis(days=90, end_date=day)
        guidance = analysis.get("hrv_guidance", {})
        summary = analysis.get("banister", {}).get("summary", {})
        features: Dict[str, float] = {}

        if guidance.get("rmssd_delta_pct") is not None:
            features["hrv_trend"] = abs(min(0.0, float(guidance["rmssd_delta_pct"])))
        if guidance.get("resting_hr_delta_bpm") is not None:
            features["resting_hr"] = abs(max(0.0, float(guidance["resting_hr_delta_bpm"])) * 4.0)
        if guidance.get("sleep_score_recent") is not None:
            features["sleep_quality"] = max(0.0, 75.0 - float(guidance["sleep_score_recent"]))
        if summary.get("load_ratio_7d_to_28d_week") is not None:
            features["training_load"] = abs(float(summary["load_ratio_7d_to_28d_week"]) - 1.0) * 40.0
        if summary.get("performance") is not None:
            features["form_balance"] = abs(min(0.0, float(summary["performance"])) * 2.0)

        ctl = self.get_ctl(day)
        atl = self.get_atl(day)
        tsb = self.get_tsb(day)
        if ctl and atl and ctl > 0:
            features["acute_chronic_ratio"] = abs(float(atl) / float(ctl) - 1.0) * 35.0
        if tsb is not None:
            features["tsb_deficit"] = abs(min(0.0, float(tsb))) * 1.5

        ef = self.get_ef_rolling(day, 30)
        if ef is not None:
            features["economy_factor"] = max(0.0, 0.004 - float(ef)) * 5000.0

        drift = analysis.get("thresholds", {}).get("drift", {})
        decoupling = drift.get("recent_median_decoupling_pct")
        if decoupling is not None:
            features["aerobic_decoupling"] = max(0.0, float(decoupling) - 5.0) * 2.0

        for flag in analysis.get("polarized_training", {}).get("flags", []):
            features[f"polarized_{flag}"] = 20.0

        if not features:
            return None, None, {}
        name = max(features, key=features.get)
        total = sum(features.values())
        weight = round(features[name] / total, 3) if total > 0 else None
        return name, weight, {key: round(value, 2) for key, value in features.items()}

    def get_sleep_debt_hours(self, day: date, window_days: int) -> Optional[float]:
        start = day - timedelta(days=window_days - 1)
        rows = (
            self.db.query(Sleep.total_sleep_time)
            .filter(and_(Sleep.sleep_date >= start, Sleep.sleep_date <= day))
            .all()
        )
        if not rows:
            return None
        debt_seconds = 0.0
        nights = 0
        for row in rows:
            if row.total_sleep_time is None:
                continue
            nights += 1
            debt_seconds += max(0.0, SLEEP_DEBT_TARGET_SECONDS - float(row.total_sleep_time))
        if nights == 0:
            return None
        return round(debt_seconds / 3600.0, 2)

    def get_critical_speed_snapshot(self, day: date) -> Tuple[Optional[float], Optional[float]]:
        if self.storage is None:
            return None, None
        service = PerformanceMetricsService(self.db, self.storage)
        payload = service.get_snapshot_payload("critical_speed")
        if not payload:
            payload = service.calculate_critical_speed()
        outdoor = payload.get("outdoor") or payload
        cs = outdoor.get("critical_speed_mps")
        w_prime = outdoor.get("d_prime")
        if cs is None:
            return None, None
        return round(float(cs), 4), round(float(w_prime), 1) if w_prime is not None else None

    def get_critical_power_snapshot(self, _day: date) -> Tuple[Optional[float], Optional[float]]:
        if self.storage is None:
            return None, None
        curves = self._duration_curve_payload().get("all_time", {}).get("curves", {})
        power_points = curves.get("power", [])
        if len(power_points) < 2:
            return None, None
        pairs = []
        for point in power_points:
            duration_s = point.get("duration_seconds")
            power = point.get("power_watts")
            if duration_s and power and duration_s > 0 and power > 0:
                pairs.append((1.0 / float(duration_s), float(power)))
        if len(pairs) < 2:
            return None, None
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        denom = sum((x - x_mean) ** 2 for x in xs)
        if denom <= 0:
            return None, None
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
        intercept = y_mean - slope * x_mean
        if slope <= 0:
            return None, None
        cp = intercept
        w_prime_power = slope
        if cp <= 0:
            return None, None
        return round(cp, 1), round(w_prime_power, 1)

    @staticmethod
    def get_form_degradation_index(activity: Activity) -> Optional[float]:
        if not is_running_activity(activity):
            return None
        penalties = []
        for value, weight in [
            (activity.pace_drop_pct, 2.0),
            (activity.hr_drift_pct, 1.5),
            (activity.cadence_drop_pct, 1.0),
            (activity.ef_drop_pct, 2.0),
        ]:
            if value is not None and float(value) > 0:
                penalties.append(float(value) * weight)
        if not penalties:
            return 0.0 if activity.fatigue_resistance_score is not None else None
        return round(min(100.0, sum(penalties)), 1)

    @staticmethod
    def get_weather_adjusted_pace(activity: Activity) -> Tuple[Optional[float], Optional[float]]:
        pace = PpapMetricsService._pace_sec_per_km(activity)
        if pace is None:
            return None, None
        temperature = activity.temperature
        humidity = activity.humidity
        wind_speed = activity.wind_speed
        penalty = 0.0
        if temperature is not None:
            if float(temperature) > 15.0:
                penalty += min(12.0, (float(temperature) - 15.0) * 0.8)
            elif float(temperature) < 5.0:
                penalty += min(8.0, (5.0 - float(temperature)) * 0.5)
        if humidity is not None and float(humidity) > 70.0:
            penalty += min(6.0, (float(humidity) - 70.0) * 0.15)
        if wind_speed is not None and float(wind_speed) > 3.0:
            penalty += min(8.0, (float(wind_speed) - 3.0) * 1.5)
        adjusted_pace = pace * (1.0 + penalty / 100.0)
        return round(adjusted_pace, 1), round(penalty, 2)

    @staticmethod
    def get_running_economy_hr(activity: Activity) -> Optional[float]:
        if activity.average_heart_rate is None or activity.average_heart_rate <= 0:
            return None
        speed_mps = PpapMetricsService._pace_to_speed_mps(activity)
        if speed_mps is None:
            return None
        return round(speed_mps / float(activity.average_heart_rate), 6)

    @staticmethod
    def get_running_economy_power(activity: Activity) -> Optional[float]:
        power = activity.normalized_power or activity.average_power
        if power is None or power <= 0:
            return None
        speed_mps = PpapMetricsService._pace_to_speed_mps(activity)
        if speed_mps is None:
            return None
        return round(speed_mps / float(power), 6)

    @staticmethod
    def _pace_to_speed_mps(activity: Activity) -> Optional[float]:
        if activity.distance and activity.duration and activity.distance > 0:
            return activity.distance / activity.duration
        if activity.average_speed and activity.average_speed > 0:
            return float(activity.average_speed)
        return None

    @staticmethod
    def _pace_sec_per_km(activity: Activity) -> Optional[float]:
        speed_mps = PpapMetricsService._pace_to_speed_mps(activity)
        if speed_mps is None or speed_mps <= 0:
            return None
        return 1000.0 / speed_mps

    def get_sleep_consistency_score(self, day: date, window_days: int = 14) -> Optional[float]:
        start = day - timedelta(days=window_days - 1)
        rows = (
            self.db.query(Sleep.sleep_date, Sleep.total_sleep_time)
            .filter(and_(Sleep.sleep_date >= start, Sleep.sleep_date <= day))
            .all()
        )
        durations = [float(r.total_sleep_time) for r in rows if r.total_sleep_time]
        if len(durations) < 3:
            return None
        std_hours = pstdev(durations) / 3600.0
        return round(max(0.0, min(100.0, 100.0 - std_hours * 12.0)), 1)
