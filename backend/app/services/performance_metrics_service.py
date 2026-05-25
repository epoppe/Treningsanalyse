from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ..database.models.activity import Activity, AnalyticsSnapshot
from ..storage import DataStorage


class PerformanceMetricsService:
    SPEED_CURVE_DURATIONS = [5, 30, 60, 180, 300, 600, 1200, 3600]
    CRITICAL_SPEED_DURATIONS = [180, 360, 720, 1200, 1800]

    def __init__(self, db: Session, storage: DataStorage):
        self.db = db
        self.storage = storage

    def _is_running_activity(self, activity: Activity) -> bool:
        if not activity.activity_type:
            return True
        type_key = (activity.activity_type.type_key or "").lower()
        parent = (activity.activity_type.parent_type_key or "").lower()
        return "running" in type_key or parent == "running"

    def _normalize_speed_mps(self, speed: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(speed, errors="coerce")
        median = numeric[numeric > 0].median()
        if pd.notna(median) and median > 8:
            return numeric / 3.6
        return numeric

    def _details_for_activity(self, activity: Activity) -> Optional[pd.DataFrame]:
        try:
            return self.storage.get_activity_details(int(activity.activity_id))
        except Exception:
            return None

    def _prepare_samples(self, details_df: pd.DataFrame, drop_warmup: bool = True) -> pd.DataFrame:
        if details_df is None or details_df.empty:
            return pd.DataFrame()
        if "timestamp" not in details_df.columns or "speed" not in details_df.columns:
            return pd.DataFrame()

        df = details_df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["speed_mps"] = self._normalize_speed_mps(df["speed"])
        if "heart_rate" in df.columns:
            df["heart_rate"] = pd.to_numeric(df["heart_rate"], errors="coerce")
        else:
            df["heart_rate"] = np.nan
        if "cadence" in df.columns:
            df["cadence"] = pd.to_numeric(df["cadence"], errors="coerce")
        else:
            df["cadence"] = np.nan
        if "power" in df.columns:
            df["power"] = pd.to_numeric(df["power"], errors="coerce")
        else:
            df["power"] = np.nan

        df = df.dropna(subset=["timestamp", "speed_mps"])
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
        df = df[df["speed_mps"] >= 0.5]
        if df.empty:
            return df

        start = df["timestamp"].iloc[0]
        if drop_warmup and (df["timestamp"].iloc[-1] - start).total_seconds() > 600:
            df = df[df["timestamp"] >= start + pd.Timedelta(seconds=600)]
        df = df.reset_index(drop=True)
        if len(df) < 2:
            return pd.DataFrame()

        elapsed = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()
        df["elapsed_s"] = elapsed
        dt = df["elapsed_s"].diff().shift(-1)
        fallback_dt = dt[(dt > 0) & (dt <= 10)].median()
        if pd.isna(fallback_dt):
            fallback_dt = 1.0
        df["dt_s"] = dt.fillna(fallback_dt).clip(lower=0.1, upper=10)
        df["distance_delta_m"] = df["speed_mps"] * df["dt_s"]
        df["cum_distance_m"] = df["distance_delta_m"].cumsum()
        return df

    def _best_average_for_duration(
        self,
        samples: pd.DataFrame,
        duration_s: int,
        value_col: str,
    ) -> Optional[Dict[str, Any]]:
        if samples.empty or len(samples) < 2 or value_col not in samples.columns:
            return None
        if samples["elapsed_s"].iloc[-1] < duration_s:
            return None

        elapsed = samples["elapsed_s"].to_numpy()
        values = pd.to_numeric(samples[value_col], errors="coerce").to_numpy()
        if np.isnan(values).all():
            return None

        if value_col == "speed_mps":
            cumulative = samples["cum_distance_m"].to_numpy()
        else:
            dt = samples["dt_s"].to_numpy()
            cumulative = np.nancumsum(np.nan_to_num(values, nan=0.0) * dt)

        best_value = None
        best_start_idx = None
        best_end_idx = None
        for start_idx, start_s in enumerate(elapsed):
            target = start_s + duration_s
            end_idx = int(np.searchsorted(elapsed, target, side="left"))
            if end_idx >= len(elapsed):
                break
            start_cum = cumulative[start_idx - 1] if start_idx > 0 else 0.0
            window_sum = cumulative[end_idx] - start_cum
            avg_value = window_sum / duration_s
            if best_value is None or avg_value > best_value:
                best_value = float(avg_value)
                best_start_idx = start_idx
                best_end_idx = end_idx

        if best_value is None:
            return None
        return {
            "duration_seconds": duration_s,
            "value": best_value,
            "start_time": samples["timestamp"].iloc[best_start_idx].isoformat(),
            "end_time": samples["timestamp"].iloc[best_end_idx].isoformat(),
        }

    def extract_activity_best_efforts(self, activity: Activity) -> List[Dict[str, Any]]:
        details = self._details_for_activity(activity)
        samples = self._prepare_samples(details, drop_warmup=True) if details is not None else pd.DataFrame()
        efforts: List[Dict[str, Any]] = []
        if samples.empty:
            return efforts

        durations = sorted(set(self.SPEED_CURVE_DURATIONS + self.CRITICAL_SPEED_DURATIONS))
        for duration_s in durations:
            speed_effort = self._best_average_for_duration(samples, duration_s, "speed_mps")
            if speed_effort:
                speed_effort.update({
                    "metric_type": "speed",
                    "activity_id": activity.activity_id,
                    "activity_name": activity.activity_name,
                    "activity_start_time": activity.start_time.isoformat() if activity.start_time else None,
                    "speed_mps": speed_effort["value"],
                    "distance_m": speed_effort["value"] * duration_s,
                })
                efforts.append(speed_effort)

            power_effort = self._best_average_for_duration(samples, duration_s, "power")
            if power_effort and power_effort["value"] > 0:
                power_effort.update({
                    "metric_type": "power",
                    "activity_id": activity.activity_id,
                    "activity_name": activity.activity_name,
                    "activity_start_time": activity.start_time.isoformat() if activity.start_time else None,
                    "power_watts": power_effort["value"],
                })
                efforts.append(power_effort)
        return efforts

    def calculate_fatigue_resistance_for_activity(
        self,
        activity: Activity,
        force_recalculate: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if activity.fatigue_resistance_score is not None and not force_recalculate:
            return {
                "activity_id": activity.activity_id,
                "fatigue_resistance_score": activity.fatigue_resistance_score,
                "pace_drop_pct": activity.pace_drop_pct,
                "hr_drift_pct": activity.hr_drift_pct,
                "cadence_drop_pct": activity.cadence_drop_pct,
                "ef_drop_pct": activity.ef_drop_pct,
                "calculation_method": "cached",
            }

        details = self._details_for_activity(activity)
        samples = self._prepare_samples(details, drop_warmup=True) if details is not None else pd.DataFrame()
        if samples.empty or len(samples) < 20:
            return None
        duration = samples["elapsed_s"].iloc[-1] - samples["elapsed_s"].iloc[0]
        if duration < 45 * 60:
            return None

        first_cut = samples["elapsed_s"].iloc[0] + duration * 0.35
        last_cut = samples["elapsed_s"].iloc[0] + duration * 0.65
        early = samples[samples["elapsed_s"] <= first_cut]
        late = samples[samples["elapsed_s"] >= last_cut]
        if len(early) < 8 or len(late) < 8:
            return None

        early_speed = early["speed_mps"].mean()
        late_speed = late["speed_mps"].mean()
        early_hr = early["heart_rate"].mean()
        late_hr = late["heart_rate"].mean()
        early_cadence = early["cadence"].mean()
        late_cadence = late["cadence"].mean()

        def pct_drop(first: float, second: float) -> Optional[float]:
            if pd.isna(first) or pd.isna(second) or first <= 0:
                return None
            return ((first - second) / first) * 100

        def pct_rise(first: float, second: float) -> Optional[float]:
            if pd.isna(first) or pd.isna(second) or first <= 0:
                return None
            return ((second - first) / first) * 100

        early_ef = early_speed / early_hr if pd.notna(early_hr) and early_hr > 0 else np.nan
        late_ef = late_speed / late_hr if pd.notna(late_hr) and late_hr > 0 else np.nan
        pace_drop_pct = pct_drop(early_speed, late_speed)
        hr_drift_pct = pct_rise(early_hr, late_hr)
        cadence_drop_pct = pct_drop(early_cadence, late_cadence)
        ef_drop_pct = pct_drop(early_ef, late_ef)

        penalty = 0.0
        for value, weight in [
            (pace_drop_pct, 2.0),
            (hr_drift_pct, 1.5),
            (cadence_drop_pct, 1.0),
            (ef_drop_pct, 2.0),
        ]:
            if value is not None and pd.notna(value) and value > 0:
                penalty += value * weight
        score = max(0.0, min(100.0, 100.0 - penalty))

        activity.fatigue_resistance_score = round(score, 1)
        activity.pace_drop_pct = round(pace_drop_pct, 2) if pace_drop_pct is not None else None
        activity.hr_drift_pct = round(hr_drift_pct, 2) if hr_drift_pct is not None else None
        activity.cadence_drop_pct = round(cadence_drop_pct, 2) if cadence_drop_pct is not None else None
        activity.ef_drop_pct = round(ef_drop_pct, 2) if ef_drop_pct is not None else None
        self.db.commit()

        return {
            "activity_id": activity.activity_id,
            "fatigue_resistance_score": activity.fatigue_resistance_score,
            "pace_drop_pct": activity.pace_drop_pct,
            "hr_drift_pct": activity.hr_drift_pct,
            "cadence_drop_pct": activity.cadence_drop_pct,
            "ef_drop_pct": activity.ef_drop_pct,
            "calculation_method": "calculated",
        }

    def _running_activities(self, days: Optional[int] = None) -> List[Activity]:
        query = self.db.query(Activity).order_by(Activity.start_time.asc())
        if days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(Activity.start_time >= cutoff)
        activities = query.all()
        return [activity for activity in activities if self._is_running_activity(activity)]

    def collect_best_efforts(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        efforts: List[Dict[str, Any]] = []
        for activity in self._running_activities(days=days):
            efforts.extend(self.extract_activity_best_efforts(activity))
        return efforts

    def build_duration_curve(self, days: Optional[int] = None) -> Dict[str, Any]:
        efforts = self.collect_best_efforts(days=days)
        curves: Dict[str, List[Dict[str, Any]]] = {"speed": [], "power": []}
        for metric_type in curves:
            metric_efforts = [e for e in efforts if e.get("metric_type") == metric_type]
            for duration_s in self.SPEED_CURVE_DURATIONS:
                candidates = [e for e in metric_efforts if e["duration_seconds"] == duration_s]
                if not candidates:
                    continue
                best = max(candidates, key=lambda e: e["value"])
                item = {
                    "duration_seconds": duration_s,
                    "activity_id": best.get("activity_id"),
                    "activity_name": best.get("activity_name"),
                    "activity_start_time": best.get("activity_start_time"),
                    "start_time": best.get("start_time"),
                    "end_time": best.get("end_time"),
                }
                if metric_type == "speed":
                    item["speed_mps"] = round(best["value"], 4)
                    item["pace_sec_per_km"] = round(1000 / best["value"], 1) if best["value"] > 0 else None
                else:
                    item["power_watts"] = round(best["value"], 1)
                curves[metric_type].append(item)
        return {
            "days": days,
            "curves": curves,
            "effort_count": len(efforts),
        }

    def calculate_critical_speed(self, days: Optional[int] = None) -> Dict[str, Any]:
        efforts = self.collect_best_efforts(days=days)
        speed_efforts = [e for e in efforts if e.get("metric_type") == "speed"]
        best_by_duration: Dict[int, Dict[str, Any]] = {}
        for duration_s in self.CRITICAL_SPEED_DURATIONS:
            candidates = [e for e in speed_efforts if e["duration_seconds"] == duration_s]
            if candidates:
                best_by_duration[duration_s] = max(candidates, key=lambda e: e["speed_mps"])

        if len(best_by_duration) < 3:
            return {
                "critical_speed_mps": None,
                "critical_pace_sec_per_km": None,
                "d_prime": None,
                "model_r2": None,
                "model_quality": "insufficient_data",
                "efforts": list(best_by_duration.values()),
            }

        times = np.array(sorted(best_by_duration.keys()), dtype=float)
        distances = np.array([best_by_duration[int(t)]["speed_mps"] * t for t in times], dtype=float)
        slope, intercept = np.polyfit(times, distances, 1)
        predictions = slope * times + intercept
        ss_res = float(np.sum((distances - predictions) ** 2))
        ss_tot = float(np.sum((distances - distances.mean()) ** 2))
        r2 = 1.0 if ss_tot == 0 else 1 - (ss_res / ss_tot)
        quality = "good" if r2 >= 0.95 else "fair" if r2 >= 0.85 else "low"
        pace = 1000 / slope if slope > 0 else None
        return {
            "critical_speed_mps": round(float(slope), 4),
            "critical_pace_sec_per_km": round(float(pace), 1) if pace else None,
            "d_prime": round(float(intercept), 1),
            "model_r2": round(float(r2), 4),
            "model_quality": quality,
            "efforts": list(best_by_duration.values()),
        }

    def _upsert_snapshot(
        self,
        metric_key: str,
        payload: Dict[str, Any],
        data_quality_score: Optional[float] = None,
        model_quality: Optional[str] = None,
    ) -> AnalyticsSnapshot:
        snapshot = self.db.query(AnalyticsSnapshot).filter_by(metric_key=metric_key).first()
        if snapshot is None:
            snapshot = AnalyticsSnapshot(metric_key=metric_key)
            self.db.add(snapshot)
        snapshot.payload = payload
        snapshot.calculated_at = datetime.now(timezone.utc)
        snapshot.data_quality_score = data_quality_score
        snapshot.model_quality = model_quality
        self.db.commit()
        return snapshot

    def recalculate_performance_snapshots(self) -> Dict[str, Any]:
        critical_speed = self.calculate_critical_speed(days=None)
        curve_all = self.build_duration_curve(days=None)
        curve_90 = self.build_duration_curve(days=90)
        curve_365 = self.build_duration_curve(days=365)
        duration_curve = {
            "all_time": curve_all,
            "last_90_days": curve_90,
            "last_365_days": curve_365,
        }

        self._upsert_snapshot(
            "critical_speed",
            critical_speed,
            data_quality_score=100.0 if critical_speed.get("critical_speed_mps") else 0.0,
            model_quality=critical_speed.get("model_quality"),
        )
        self._upsert_snapshot(
            "duration_curve",
            duration_curve,
            data_quality_score=100.0 if curve_all["effort_count"] else 0.0,
            model_quality="available" if curve_all["effort_count"] else "insufficient_data",
        )
        return {
            "critical_speed": critical_speed,
            "duration_curve": duration_curve,
        }

    def get_snapshot_payload(self, metric_key: str) -> Optional[Dict[str, Any]]:
        snapshot = self.db.query(AnalyticsSnapshot).filter_by(metric_key=metric_key).first()
        if not snapshot:
            return None
        payload = snapshot.payload or {}
        payload["calculated_at"] = snapshot.calculated_at.isoformat() if snapshot.calculated_at else None
        payload["data_quality_score"] = snapshot.data_quality_score
        payload["model_quality"] = snapshot.model_quality
        return payload
