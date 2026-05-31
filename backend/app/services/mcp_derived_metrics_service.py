from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median, pstdev
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, selectinload

from ..database.models import HRV, Sleep
from ..database.models.activity import Activity, GarminPerformanceMetric
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity
from .coaching_analysis_service import CoachingAnalysisService
from .performance_metrics_service import PerformanceMetricsService
from .ppap_metrics_service import (
    COACHING_ZONE_METRICS,
    DURATION_CURVE_METRICS,
    PpapMetricsService,
    READINESS_COMPONENT_METRICS,
)


RACE_DISTANCES_M = {
    "predicted_5k_time": 5000.0,
    "predicted_10k_time": 10000.0,
    "predicted_half_marathon_time": 21097.5,
    "predicted_marathon_time": 42195.0,
}


class McpDerivedMetricsService:
    """Computed metrics for MCP that are not stored as simple DB columns."""

    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage
        self._coaching_cache: Dict[Tuple[date, int], Dict[str, Any]] = {}
        self._cs_cache: Optional[Dict[str, Any]] = None
        self._ppap = PpapMetricsService(db, storage)

    def metric_definition(self, metric_key: str) -> Optional[Dict[str, Any]]:
        return DERIVED_METRIC_CATALOG.get(metric_key)

    def get_readiness_composites(self, day: Optional[date] = None) -> Dict[str, Any]:
        target = day or date.today()
        return {
            "date": target.isoformat(),
            "fitness_score": self._daily_metric_value("fitness_score", target),
            "fatigue_score": self._daily_metric_value("fatigue_score", target),
            "readiness_score": self._daily_metric_value("readiness_score", target),
            "recovery_score": self._daily_metric_value("recovery_score", target),
            "performance_score": self._daily_metric_value("performance_score", target),
            "injury_risk_score": self._daily_metric_value("injury_risk_score", target),
            "overtraining_score": self._daily_metric_value("overtraining_score", target),
            "fitness_ctl": self._ppap.get_ctl(target),
            "fitness_atl": self._ppap.get_atl(target),
            "fitness_tsb": self._ppap.get_tsb(target),
            "recovery_hrv_baseline": self._ppap.get_hrv_baseline(target),
            "recovery_hrv_delta_pct": self._ppap.get_hrv_delta_pct(target),
        }

    def list_metric_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": key,
                "category": definition["category"],
                "unit": definition["unit"],
                "scope": definition["scope"],
                "source": "derived",
                "heuristic": definition.get("heuristic", False),
            }
            for key, definition in sorted(DERIVED_METRIC_CATALOG.items())
        ]

    def query_timeseries(
        self,
        metric_key: str,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 365,
    ) -> Dict[str, Any]:
        definition = self.metric_definition(metric_key)
        if definition is None:
            return {"status": "unknown_metric", "metric_key": metric_key}

        end = end_date or date.today()
        start = start_date or (end - timedelta(days=limit - 1))
        if start > end:
            start, end = end, start

        scope = definition["scope"]
        if scope == "activity":
            points = self._activity_scope_series(metric_key, start, end, limit)
        elif scope == "snapshot":
            points = self._snapshot_series(metric_key, end)
        elif scope == "rolling_daily":
            points = self._rolling_daily_scope_series(metric_key, start, end, limit)
        else:
            points = self._daily_scope_series(metric_key, start, end, limit)

        points = [point for point in points if point.get("value") is not None][-limit:]
        return {
            "status": "ok",
            "metric_key": metric_key,
            "category": definition["category"],
            "unit": definition["unit"],
            "scope": scope,
            "heuristic": definition.get("heuristic", False),
            "points": points,
            "count": len(points),
        }

    def _daily_scope_series(
        self,
        metric_key: str,
        start: date,
        end: date,
        limit: int,
    ) -> List[Dict[str, Any]]:
        dates = []
        current = end
        while current >= start and len(dates) < limit:
            dates.append(current)
            current -= timedelta(days=1)
        dates.reverse()

        points = []
        for day in dates:
            value = self._daily_metric_value(metric_key, day)
            if value is None:
                continue
            points.append({"date": day.isoformat(), "timestamp": None, "value": value})
        return points

    def _snapshot_series(self, metric_key: str, end: date) -> List[Dict[str, Any]]:
        value = self._daily_metric_value(metric_key, end)
        if value is None:
            return []
        return [{"date": end.isoformat(), "timestamp": None, "value": value}]

    def _activity_scope_series(
        self,
        metric_key: str,
        start: date,
        end: date,
        limit: int,
    ) -> List[Dict[str, Any]]:
        activities = (
            self.db.query(Activity)
            .options(selectinload(Activity.activity_type))
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= end,
                )
            )
            .order_by(Activity.start_time.desc())
            .limit(max(limit, 200))
            .all()
        )
        points: List[Dict[str, Any]] = []
        for activity in activities:
            if not is_running_activity(activity):
                continue
            value = self._activity_metric_value(metric_key, activity)
            if value is None:
                continue
            points.append(
                {
                    "date": activity.start_time.date().isoformat() if activity.start_time else None,
                    "timestamp": activity.start_time.isoformat() if activity.start_time else None,
                    "value": value,
                    "activity_id": activity.activity_id,
                    "activity_name": activity.activity_name,
                    "activity_type": activity.activity_type.type_key if activity.activity_type else None,
                }
            )
            if len(points) >= limit:
                break
        return list(reversed(points))

    def _daily_metric_value(self, metric_key: str, day: date) -> Any:
        if metric_key == "fitness.ctl":
            return self._ppap.get_ctl(day)
        if metric_key == "fitness.atl":
            return self._ppap.get_atl(day)
        if metric_key in {"fitness.tsb", "fitness.form"}:
            return self._ppap.get_tsb(day)
        if metric_key in {"fitness.ef_30d", "fitness.ef_60d", "fitness.ef_90d"}:
            window = int(metric_key.rsplit("_", 1)[-1].replace("d", ""))
            return self._ppap.get_ef_rolling(day, window)
        if metric_key == "recovery.hrv_baseline":
            return self._ppap.get_hrv_baseline(day)
        if metric_key == "recovery.hrv_delta_pct":
            return self._ppap.get_hrv_delta_pct(day)
        if metric_key == "recovery.recovery_efficiency_score":
            return self._recovery_efficiency_score(day)
        if metric_key in {"cardio.rhr_7d", "cardio.rhr_30d"}:
            window = int(metric_key.rsplit("_", 1)[-1].replace("d", ""))
            return self._ppap.get_rhr_rolling(day, window)
        if metric_key == "running.critical_speed":
            cs, _w = self._ppap.get_critical_speed_snapshot(day)
            return cs
        if metric_key == "running.w_prime":
            _cs, w_prime = self._ppap.get_critical_speed_snapshot(day)
            return w_prime

        if metric_key in DURATION_CURVE_METRICS:
            return self._ppap.get_duration_curve_value(metric_key, day)
        if metric_key in COACHING_ZONE_METRICS:
            return self._ppap.get_coaching_zone_pct(day, metric_key)
        if metric_key in READINESS_COMPONENT_METRICS:
            return self._ppap.get_readiness_component(day, metric_key)
        if metric_key == "sleep.sleep_debt_7d":
            return self._ppap.get_sleep_debt_hours(day, 7)
        if metric_key == "sleep.sleep_debt_14d":
            return self._ppap.get_sleep_debt_hours(day, 14)
        if metric_key == "sleep.sleep_debt_28d":
            return self._ppap.get_sleep_debt_hours(day, 28)
        if metric_key == "sleep.consistency_score":
            return self._ppap.get_sleep_consistency_score(day)
        if metric_key == "recovery.predicted_hours_to_baseline":
            return self._ppap.get_predicted_recovery_hours(day)
        if metric_key.startswith("training.class_") and metric_key.endswith("_pct"):
            return self._ppap.get_training_class_pct(day, metric_key)

        if metric_key == "running.critical_power":
            cp, _wp = self._ppap.get_critical_power_snapshot(day)
            return cp
        if metric_key == "running.w_prime_power":
            _cp, wp = self._ppap.get_critical_power_snapshot(day)
            return wp


        if metric_key in {"cardio.hrv_7d", "cardio.hrv_30d", "cardio.hrv_90d"}:
            window = int(metric_key.rsplit("_", 1)[-1].replace("d", ""))
            return self._hrv_rolling(day, window)

        if metric_key == "cardio.drift_score":
            return self._cardio_drift_score(day)

        if metric_key == "load.acwr":
            return self._load_acwr(day)

        if metric_key in {"load.monotony", "load.strain"}:
            monotony, strain = self._load_monotony_strain(day)
            return monotony if metric_key == "load.monotony" else strain

        if metric_key in {"risk.overtraining_score", "overtraining_score"}:
            return self._overtraining_score(day)

        if metric_key.startswith("predicted_"):
            return self._predicted_race_time(metric_key, day)

        if metric_key in {"training.aerobic_score", "training.anaerobic_score"}:
            aerobic, anaerobic = self._training_load_scores(day)
            return aerobic if metric_key == "training.aerobic_score" else anaerobic

        if metric_key == "performance_driver_name":
            name, _weight = self._performance_driver(day)
            return name

        if metric_key == "performance_driver_weight":
            _name, weight = self._performance_driver(day)
            return weight

        if metric_key == "fitness_score":
            return self._banister_scores(day)[0]

        if metric_key == "fatigue_score":
            return self._banister_scores(day)[1]

        if metric_key == "performance_score":
            return self._banister_scores(day)[2]

        if metric_key == "recovery_score":
            return self._recovery_score(day)

        if metric_key == "readiness_score":
            return self._readiness_score(day)

        if metric_key == "injury_risk_score":
            return self._injury_risk_score(day)

        return None

    def _activity_metric_value(self, metric_key: str, activity: Activity) -> Any:
        if metric_key.startswith("route."):
            return self._route_delta(metric_key, activity)

        if metric_key == "weather.adjusted_pace":
            pace, _penalty = self._weather_pace(activity)
            return pace

        if metric_key == "weather.performance_penalty_pct":
            _pace, penalty = self._weather_pace(activity)
            return penalty

        if metric_key == "training.training_zone":
            return self._training_zone(activity)

        if metric_key == "running.economy_hr":
            return self._ppap.get_running_economy_hr(activity)

        if metric_key == "running.economy_power":
            return self._ppap.get_running_economy_power(activity)

        if metric_key == "training.training_class":
            day = activity.start_time.date() if activity.start_time else date.today()
            return self._ppap.get_training_class_for_activity(activity, day)

        if metric_key == "running.form_degradation_index":
            return self._ppap.get_form_degradation_index(activity)


        return None

    def _coaching(self, day: date, days: int = 90) -> Dict[str, Any]:
        key = (day, days)
        if key not in self._coaching_cache:
            service = CoachingAnalysisService(self.db, self.storage)
            self._coaching_cache[key] = service.build_coaching_analysis(days=days, end_date=day)
        return self._coaching_cache[key]

    def _hrv_rolling(self, day: date, window_days: int) -> Optional[float]:
        start = day - timedelta(days=window_days - 1)
        rows = (
            self.db.query(HRV.rmssd)
            .filter(
                and_(
                    HRV.measurement_date >= start,
                    HRV.measurement_date <= day,
                    HRV.rmssd.isnot(None),
                )
            )
            .all()
        )
        values = [float(row.rmssd) for row in rows if row.rmssd is not None]
        if not values:
            return None
        return round(mean(values), 1)

    def _cardio_drift_score(self, day: date) -> Optional[float]:
        start = day - timedelta(days=13)
        rows = (
            self.db.query(Activity.hr_drift_pct, Activity.decoupling_percent)
            .filter(
                and_(
                    func.date(Activity.start_time) >= start,
                    func.date(Activity.start_time) <= day,
                )
            )
            .all()
        )
        drift_values = []
        for hr_drift, decoupling in rows:
            if hr_drift is not None:
                drift_values.append(float(hr_drift))
            elif decoupling is not None:
                drift_values.append(float(decoupling))
        if not drift_values:
            analysis = self._coaching(day)
            median = analysis.get("thresholds", {}).get("drift", {}).get("recent_median_hr_drift_pct")
            if median is None:
                median = analysis.get("thresholds", {}).get("drift", {}).get("recent_median_decoupling_pct")
            if median is None:
                return None
            drift_values = [float(median)]
        median_drift = median(drift_values)
        return round(max(0.0, min(100.0, 100.0 - median_drift * 2.5)), 1)

    def _garmin_row(self, day: date) -> Optional[GarminPerformanceMetric]:
        return (
            self.db.query(GarminPerformanceMetric)
            .filter(func.date(GarminPerformanceMetric.date) <= day)
            .order_by(GarminPerformanceMetric.date.desc())
            .first()
        )

    def _load_acwr(self, day: date) -> Optional[float]:
        row = self._garmin_row(day)
        if row is not None:
            if row.daily_acute_chronic_workload_ratio is not None:
                return round(float(row.daily_acute_chronic_workload_ratio), 3)
            if row.acwr_percent is not None:
                return round(float(row.acwr_percent) / 100.0, 3)
        analysis = self._coaching(day)
        ratio = analysis.get("banister", {}).get("summary", {}).get("load_ratio_7d_to_28d_week")
        return round(float(ratio), 3) if ratio is not None else None

    def _load_monotony_strain(self, day: date) -> Tuple[Optional[float], Optional[float]]:
        start = day - timedelta(days=6)
        analysis = self._coaching(day, days=90)
        daily_rows = analysis.get("banister", {}).get("daily", [])
        loads = [
            float(row["load"])
            for row in daily_rows
            if start.isoformat() <= row["date"] <= day.isoformat()
        ]
        if len(loads) < 3:
            return None, None
        avg_load = mean(loads)
        std_load = pstdev(loads)
        if std_load <= 0:
            return None, None
        monotony = avg_load / std_load
        strain = sum(loads) * monotony
        return round(monotony, 2), round(strain, 1)

    def _banister_scores(self, day: date) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        summary = self._coaching(day).get("banister", {}).get("summary", {})
        fitness = summary.get("fitness")
        fatigue = summary.get("fatigue")
        performance = summary.get("performance")
        if fitness is None or fatigue is None or performance is None:
            return None, None, None
        return (
            round(max(0.0, min(100.0, float(fitness) / 1.5)), 1),
            round(max(0.0, min(100.0, float(fatigue) / 1.5)), 1),
            round(max(0.0, min(100.0, 50.0 + float(performance))), 1),
        )

    def _recovery_score(self, day: date) -> Optional[float]:
        guidance = self._coaching(day).get("hrv_guidance", {})
        rmssd_delta = guidance.get("rmssd_delta_pct")
        sleep_score = guidance.get("sleep_score_recent")
        rhr_delta = guidance.get("resting_hr_delta_bpm")

        components = []
        if rmssd_delta is not None:
            components.append(max(0.0, min(100.0, 70.0 + float(rmssd_delta))))
        if sleep_score is not None:
            components.append(float(sleep_score))
        if rhr_delta is not None:
            components.append(max(0.0, min(100.0, 80.0 - float(rhr_delta) * 5.0)))

        recent_sleep = (
            self.db.query(Sleep.recovery_score, Sleep.overall_score, Sleep.sleep_score)
            .filter(and_(Sleep.sleep_date >= day - timedelta(days=2), Sleep.sleep_date <= day))
            .order_by(Sleep.sleep_date.desc())
            .first()
        )
        if recent_sleep:
            sleep_recovery = recent_sleep.recovery_score or recent_sleep.overall_score or recent_sleep.sleep_score
            if sleep_recovery is not None:
                components.append(float(sleep_recovery))

        if not components:
            return None
        return round(mean(components), 1)

    def _readiness_score(self, day: date) -> Optional[float]:
        stored = (
            self.db.query(Activity.training_readiness_score)
            .filter(
                and_(
                    func.date(Activity.start_time) == day,
                    Activity.training_readiness_score.isnot(None),
                )
            )
            .order_by(Activity.start_time.desc())
            .first()
        )
        if stored and stored.training_readiness_score is not None:
            return round(float(stored.training_readiness_score), 1)

        fitness, fatigue, performance = self._banister_scores(day)
        recovery = self._recovery_score(day)
        parts = [score for score in [recovery, performance] if score is not None]
        if fitness is not None and fatigue is not None:
            parts.append(max(0.0, min(100.0, fitness - fatigue * 0.35 + 25.0)))
        if not parts:
            return None
        return round(mean(parts), 1)

    def _overtraining_score(self, day: date) -> Optional[float]:
        analysis = self._coaching(day)
        summary = analysis.get("banister", {}).get("summary", {})
        guidance = analysis.get("hrv_guidance", {})
        acwr = self._load_acwr(day)
        monotony, strain = self._load_monotony_strain(day)

        risk = 0.0
        weights = 0.0
        performance = summary.get("performance")
        if performance is not None:
            risk += max(0.0, min(40.0, (10.0 - float(performance)) * 2.0))
            weights += 40.0
        if acwr is not None:
            risk += max(0.0, min(30.0, (float(acwr) - 1.0) * 30.0))
            weights += 30.0
        if monotony is not None:
            risk += max(0.0, min(15.0, (float(monotony) - 1.5) * 10.0))
            weights += 15.0
        if strain is not None:
            risk += max(0.0, min(15.0, (float(strain) - 3000.0) / 200.0))
            weights += 15.0
        risk += min(20.0, len(guidance.get("flags", [])) * 7.0)
        weights += 20.0

        if weights <= 0:
            return None
        return round(max(0.0, min(100.0, risk / weights * 100.0)), 1)

    def _injury_risk_score(self, day: date) -> Optional[float]:
        overtraining = self._overtraining_score(day)
        acwr = self._load_acwr(day)
        monotony, _strain = self._load_monotony_strain(day)
        if overtraining is None and acwr is None and monotony is None:
            return None

        parts = []
        if overtraining is not None:
            parts.append(float(overtraining) * 0.6)
        if acwr is not None:
            parts.append(max(0.0, min(100.0, (float(acwr) - 0.8) * 70.0)))
        if monotony is not None:
            parts.append(max(0.0, min(100.0, (float(monotony) - 1.2) * 35.0)))
        return round(max(0.0, min(100.0, mean(parts))), 1)

    def _training_load_scores(self, day: date) -> Tuple[Optional[float], Optional[float]]:
        row = self._garmin_row(day)
        if row is not None:
            aerobic = (row.monthly_load_aerobic_low or 0.0) + (row.monthly_load_aerobic_high or 0.0)
            anaerobic = row.monthly_load_anaerobic or 0.0
            total = aerobic + anaerobic
            if total > 0:
                return (
                    round(max(0.0, min(100.0, aerobic / total * 100.0)), 1),
                    round(max(0.0, min(100.0, anaerobic / total * 100.0)), 1),
                )

        start = day - timedelta(days=27)
        activities = (
            self.db.query(Activity.total_training_effect, Activity.total_anaerobic_training_effect)
            .filter(and_(func.date(Activity.start_time) >= start, func.date(Activity.start_time) <= day))
            .all()
        )
        aerobic_values = [float(row.total_training_effect) for row in activities if row.total_training_effect]
        anaerobic_values = [
            float(row.total_anaerobic_training_effect)
            for row in activities
            if row.total_anaerobic_training_effect
        ]
        if not aerobic_values and not anaerobic_values:
            return None, None
        aerobic_avg = mean(aerobic_values) if aerobic_values else 0.0
        anaerobic_avg = mean(anaerobic_values) if anaerobic_values else 0.0
        return (
            round(max(0.0, min(100.0, aerobic_avg / 5.0 * 100.0)), 1),
            round(max(0.0, min(100.0, anaerobic_avg / 5.0 * 100.0)), 1),
        )

    def _performance_driver(self, day: date) -> Tuple[Optional[str], Optional[float]]:
        name, weight, _features = self._ppap.extended_performance_driver(day)
        return name, weight

    def _critical_speed(self) -> Dict[str, Any]:
        if self._cs_cache is None:
            if self.storage is None:
                self._cs_cache = {}
            else:
                service = PerformanceMetricsService(self.db, self.storage)
                self._cs_cache = service.calculate_critical_speed()
        return self._cs_cache

    def _predicted_race_time(self, metric_key: str, day: date) -> Optional[float]:
        if self.storage is None:
            return None
        cs_payload = self._critical_speed()
        cs = cs_payload.get("critical_speed_mps")
        d_prime = cs_payload.get("d_prime")
        distance_m = RACE_DISTANCES_M.get(metric_key)
        if cs is None or d_prime is None or distance_m is None or float(cs) <= 0:
            return None
        time_s = (distance_m - float(d_prime)) / float(cs)
        if time_s <= 0 or not math.isfinite(time_s):
            return None
        return round(time_s, 1)

    def _route_delta(self, metric_key: str, activity: Activity) -> Optional[float]:
        if not is_running_activity(activity) or not activity.start_time:
            return None
        from .route_analysis_service import RouteAnalysisService

        if self.storage is None:
            return None
        service = RouteAnalysisService(self.storage)
        matches = service.get_activity_matches(activity.activity_id, self.db, same_route_only=True, limit=20)
        historical_ids = [str(match["activityId"]) for match in matches if str(match["activityId"]) != str(activity.activity_id)]
        if not historical_ids:
            return None

        historical = (
            self.db.query(Activity)
            .filter(Activity.activity_id.in_(historical_ids))
            .all()
        )
        if not historical:
            return None

        if metric_key == "route.performance_delta_pct":
            current = self._pace_sec_per_km(activity)
            baseline_values = [self._pace_sec_per_km(row) for row in historical]
            baseline_values = [value for value in baseline_values if value]
            if current is None or not baseline_values:
                return None
            baseline = mean(baseline_values)
            return round((current - baseline) / baseline * 100.0, 2)

        if metric_key == "route.hr_delta_pct":
            if activity.average_heart_rate is None:
                return None
            baseline_values = [row.average_heart_rate for row in historical if row.average_heart_rate]
            if not baseline_values:
                return None
            baseline = mean(baseline_values)
            return round((float(activity.average_heart_rate) - baseline) / baseline * 100.0, 2)

        if metric_key == "route.power_delta_pct":
            current = activity.average_power or activity.normalized_power
            baseline_values = [
                row.average_power or row.normalized_power
                for row in historical
                if (row.average_power or row.normalized_power)
            ]
            if current is None or not baseline_values:
                return None
            baseline = mean(baseline_values)
            return round((float(current) - baseline) / baseline * 100.0, 2)

        return None

    def _weather_pace(self, activity: Activity) -> Tuple[Optional[float], Optional[float]]:
        return self._ppap.get_weather_adjusted_pace(activity)


    def _training_zone(self, activity: Activity) -> Optional[float]:
        if not activity.average_heart_rate:
            return None
        day = activity.start_time.date() if activity.start_time else date.today()
        thresholds = self._coaching(day).get("thresholds", {})
        lt1 = thresholds.get("lt1", {}).get("heart_rate_bpm")
        lt2 = thresholds.get("lt2", {}).get("heart_rate_bpm")
        if lt1 is None or lt2 is None:
            return None
        hr = float(activity.average_heart_rate)
        if hr <= float(lt1):
            return 1.0
        if hr <= float(lt2):
            return 2.0
        return 3.0

    @staticmethod
    def _pace_sec_per_km(activity: Activity) -> Optional[float]:
        if activity.distance and activity.duration and activity.distance > 0:
            return activity.duration / (activity.distance / 1000.0)
        if activity.average_speed and activity.average_speed > 0:
            return 1000.0 / activity.average_speed
        return None


DERIVED_METRIC_CATALOG: Dict[str, Dict[str, Any]] = {
    "fitness.ctl": {"category": "fitness", "unit": "load", "scope": "daily", "heuristic": False},
    "fitness.atl": {"category": "fitness", "unit": "load", "scope": "daily", "heuristic": False},
    "fitness.tsb": {"category": "fitness", "unit": "load", "scope": "daily", "heuristic": False},
    "fitness.form": {"category": "fitness", "unit": "load", "scope": "daily", "heuristic": False},
    "fitness.ef_30d": {"category": "fitness", "unit": "m_per_s_per_bpm", "scope": "daily", "heuristic": False},
    "fitness.ef_60d": {"category": "fitness", "unit": "m_per_s_per_bpm", "scope": "daily", "heuristic": False},
    "fitness.ef_90d": {"category": "fitness", "unit": "m_per_s_per_bpm", "scope": "daily", "heuristic": False},
    "recovery.hrv_baseline": {"category": "recovery", "unit": "ms", "scope": "daily", "heuristic": False},
    "recovery.hrv_delta_pct": {"category": "recovery", "unit": "%", "scope": "daily", "heuristic": False},
    "recovery.recovery_efficiency_score": {"category": "recovery", "unit": "score", "scope": "daily", "heuristic": True},
    "cardio.rhr_7d": {"category": "cardio", "unit": "bpm", "scope": "daily", "heuristic": False},
    "cardio.rhr_30d": {"category": "cardio", "unit": "bpm", "scope": "daily", "heuristic": False},
    "running.critical_speed": {"category": "running", "unit": "m/s", "scope": "snapshot", "heuristic": False},
    "running.w_prime": {"category": "running", "unit": "m", "scope": "snapshot", "heuristic": False},
    "running.economy_hr": {"category": "running", "unit": "ratio", "scope": "activity", "heuristic": False},
    "running.economy_power": {"category": "running", "unit": "ratio", "scope": "activity", "heuristic": False},
    "coaching.zone1_pct": {"category": "coaching", "unit": "%", "scope": "daily", "heuristic": False},
    "coaching.zone2_pct": {"category": "coaching", "unit": "%", "scope": "daily", "heuristic": False},
    "coaching.zone3_pct": {"category": "coaching", "unit": "%", "scope": "daily", "heuristic": False},
    "readiness.total_score": {"category": "readiness", "unit": "score", "scope": "daily", "heuristic": False},
    "recovery.predicted_hours_to_baseline": {
        "category": "recovery",
        "unit": "hours",
        "scope": "daily",
        "heuristic": True,
    },
    "training.training_class": {"category": "training", "unit": "class", "scope": "activity", "heuristic": False},
    "training.class_1_pct": {"category": "training", "unit": "%", "scope": "daily", "heuristic": False},
    "training.class_2_pct": {"category": "training", "unit": "%", "scope": "daily", "heuristic": False},
    "training.class_3_pct": {"category": "training", "unit": "%", "scope": "daily", "heuristic": False},
    "training.class_4_pct": {"category": "training", "unit": "%", "scope": "daily", "heuristic": False},
    "training.class_5_pct": {"category": "training", "unit": "%", "scope": "daily", "heuristic": False},
    "training.class_6_pct": {"category": "training", "unit": "%", "scope": "daily", "heuristic": False},
    "training.class_7_pct": {"category": "training", "unit": "%", "scope": "daily", "heuristic": False},
    "training.class_8_pct": {"category": "training", "unit": "%", "scope": "daily", "heuristic": False},
    "running.power_30s_hist": {"category": "running", "unit": "W", "scope": "rolling_daily", "heuristic": False},
    "running.power_1m_hist": {"category": "running", "unit": "W", "scope": "rolling_daily", "heuristic": False},
    "running.power_3m_hist": {"category": "running", "unit": "W", "scope": "rolling_daily", "heuristic": False},
    "running.power_5m_hist": {"category": "running", "unit": "W", "scope": "rolling_daily", "heuristic": False},
    "running.power_10m_hist": {"category": "running", "unit": "W", "scope": "rolling_daily", "heuristic": False},
    "running.power_20m_hist": {"category": "running", "unit": "W", "scope": "rolling_daily", "heuristic": False},
    "running.power_40m_hist": {"category": "running", "unit": "W", "scope": "rolling_daily", "heuristic": False},
    "running.power_60m_hist": {"category": "running", "unit": "W", "scope": "rolling_daily", "heuristic": False},
    "running.speed_30s_hist": {"category": "running", "unit": "m/s", "scope": "rolling_daily", "heuristic": False},
    "running.speed_1m_hist": {"category": "running", "unit": "m/s", "scope": "rolling_daily", "heuristic": False},
    "running.speed_3m_hist": {"category": "running", "unit": "m/s", "scope": "rolling_daily", "heuristic": False},
    "running.speed_5m_hist": {"category": "running", "unit": "m/s", "scope": "rolling_daily", "heuristic": False},
    "running.speed_10m_hist": {"category": "running", "unit": "m/s", "scope": "rolling_daily", "heuristic": False},
    "running.speed_20m_hist": {"category": "running", "unit": "m/s", "scope": "rolling_daily", "heuristic": False},
    "running.speed_40m_hist": {"category": "running", "unit": "m/s", "scope": "rolling_daily", "heuristic": False},
    "running.speed_60m_hist": {"category": "running", "unit": "m/s", "scope": "rolling_daily", "heuristic": False},
    "readiness.sleep_component": {"category": "readiness", "unit": "score", "scope": "daily", "heuristic": False},
    "readiness.hrv_component": {"category": "readiness", "unit": "score", "scope": "daily", "heuristic": False},
    "readiness.form_component": {"category": "readiness", "unit": "score", "scope": "daily", "heuristic": False},
    "sleep.sleep_debt_7d": {"category": "sleep", "unit": "hours", "scope": "daily", "heuristic": False},
    "sleep.sleep_debt_14d": {"category": "sleep", "unit": "hours", "scope": "daily", "heuristic": False},
    "sleep.sleep_debt_28d": {"category": "sleep", "unit": "hours", "scope": "daily", "heuristic": False},
    "sleep.consistency_score": {"category": "sleep", "unit": "score", "scope": "daily", "heuristic": True},
    "running.critical_power": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.w_prime_power": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.form_degradation_index": {"category": "running", "unit": "score", "scope": "activity", "heuristic": False},
    "running.power_30s": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.power_1m": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.power_3m": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.power_5m": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.power_10m": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.power_20m": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.power_40m": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.power_60m": {"category": "running", "unit": "W", "scope": "snapshot", "heuristic": False},
    "running.speed_30s": {"category": "running", "unit": "m/s", "scope": "snapshot", "heuristic": False},
    "running.speed_1m": {"category": "running", "unit": "m/s", "scope": "snapshot", "heuristic": False},
    "running.speed_3m": {"category": "running", "unit": "m/s", "scope": "snapshot", "heuristic": False},
    "running.speed_5m": {"category": "running", "unit": "m/s", "scope": "snapshot", "heuristic": False},
    "running.speed_10m": {"category": "running", "unit": "m/s", "scope": "snapshot", "heuristic": False},
    "running.speed_20m": {"category": "running", "unit": "m/s", "scope": "snapshot", "heuristic": False},
    "running.speed_40m": {"category": "running", "unit": "m/s", "scope": "snapshot", "heuristic": False},
    "running.speed_60m": {"category": "running", "unit": "m/s", "scope": "snapshot", "heuristic": False},
    "cardio.hrv_7d": {"category": "cardio", "unit": "ms", "scope": "daily", "heuristic": False},
    "cardio.hrv_30d": {"category": "cardio", "unit": "ms", "scope": "daily", "heuristic": False},
    "cardio.hrv_90d": {"category": "cardio", "unit": "ms", "scope": "daily", "heuristic": False},
    "cardio.drift_score": {"category": "cardio", "unit": "score", "scope": "daily", "heuristic": True},
    "load.acwr": {"category": "training_load", "unit": "ratio", "scope": "daily", "heuristic": False},
    "load.monotony": {"category": "training_load", "unit": "ratio", "scope": "daily", "heuristic": False},
    "load.strain": {"category": "training_load", "unit": "score", "scope": "daily", "heuristic": False},
    "risk.overtraining_score": {"category": "risk", "unit": "score", "scope": "daily", "heuristic": True},
    "route.performance_delta_pct": {"category": "route", "unit": "%", "scope": "activity", "heuristic": False},
    "route.hr_delta_pct": {"category": "route", "unit": "%", "scope": "activity", "heuristic": False},
    "route.power_delta_pct": {"category": "route", "unit": "%", "scope": "activity", "heuristic": False},
    "weather.adjusted_pace": {"category": "weather", "unit": "s/km", "scope": "activity", "heuristic": True},
    "weather.performance_penalty_pct": {"category": "weather", "unit": "%", "scope": "activity", "heuristic": True},
    "predicted_5k_time": {"category": "performance", "unit": "s", "scope": "snapshot", "heuristic": True},
    "predicted_10k_time": {"category": "performance", "unit": "s", "scope": "snapshot", "heuristic": True},
    "predicted_half_marathon_time": {"category": "performance", "unit": "s", "scope": "snapshot", "heuristic": True},
    "predicted_marathon_time": {"category": "performance", "unit": "s", "scope": "snapshot", "heuristic": True},
    "training.training_zone": {"category": "training", "unit": "zone", "scope": "activity", "heuristic": False},
    "training.aerobic_score": {"category": "training", "unit": "score", "scope": "daily", "heuristic": False},
    "training.anaerobic_score": {"category": "training", "unit": "score", "scope": "daily", "heuristic": False},
    "performance_driver_name": {"category": "coaching", "unit": "label", "scope": "snapshot", "heuristic": True},
    "performance_driver_weight": {"category": "coaching", "unit": "ratio", "scope": "snapshot", "heuristic": True},
    "fitness_score": {"category": "coaching", "unit": "score", "scope": "daily", "heuristic": True},
    "fatigue_score": {"category": "coaching", "unit": "score", "scope": "daily", "heuristic": True},
    "recovery_score": {"category": "coaching", "unit": "score", "scope": "daily", "heuristic": True},
    "readiness_score": {"category": "coaching", "unit": "score", "scope": "daily", "heuristic": True},
    "performance_score": {"category": "coaching", "unit": "score", "scope": "daily", "heuristic": True},
    "injury_risk_score": {"category": "risk", "unit": "score", "scope": "daily", "heuristic": True},
    "overtraining_score": {"category": "risk", "unit": "score", "scope": "daily", "heuristic": True},
}
