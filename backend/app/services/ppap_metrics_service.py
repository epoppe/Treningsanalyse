from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database.models import HRV, RestingHeartRate
from ..database.models.activity import Activity
from ..utils.activity_filters import is_running_activity
from .performance_metrics_service import PerformanceMetricsService
from .training_stress_service import TrainingStressService


class PpapMetricsService:
    """PPAP-aligned metrics (CTL/ATL/TSB, rollups) shared by MCP and REST."""

    CTL_TAU_DAYS = 42
    ATL_TAU_DAYS = 7
    HRV_BASELINE_DAYS = 28
    LOAD_WARMUP_DAYS = 400

    def __init__(self, db: Session, storage: Optional[Any] = None):
        self.db = db
        self.storage = storage
        self._tss_service = TrainingStressService(db)
        self._load_by_date: Optional[Dict[str, Dict[str, float]]] = None
        self._load_series_end: Optional[date] = None

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

    @staticmethod
    def get_running_economy_hr(activity: Activity) -> Optional[float]:
        if activity.average_heart_rate is None or activity.average_heart_rate <= 0:
            return None
        speed_mps = None
        if activity.distance and activity.duration and activity.distance > 0:
            speed_mps = activity.distance / activity.duration
        elif activity.average_speed and activity.average_speed > 0:
            speed_mps = float(activity.average_speed)
        if speed_mps is None:
            return None
        return round(speed_mps / float(activity.average_heart_rate), 6)

    @staticmethod
    def get_running_economy_power(activity: Activity) -> Optional[float]:
        power = activity.normalized_power or activity.average_power
        if power is None or power <= 0:
            return None
        speed_mps = None
        if activity.distance and activity.duration and activity.distance > 0:
            speed_mps = activity.distance / activity.duration
        elif activity.average_speed and activity.average_speed > 0:
            speed_mps = float(activity.average_speed)
        if speed_mps is None:
            return None
        return round(speed_mps / float(power), 6)
