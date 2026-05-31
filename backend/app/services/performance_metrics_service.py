from __future__ import annotations

import math
from datetime import date, datetime, time, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ..database.models.activity import Activity, AnalyticsSnapshot
from ..storage import DataStorage
from ..utils.activity_filters import is_running_activity


class PerformanceMetricsService:
    SPEED_CURVE_DURATIONS = [30, 60, 180, 300, 600, 1200, 2400, 3600]
    CRITICAL_SPEED_DURATIONS = [180, 360, 720, 1200, 1800]
    CRITICAL_SPEED_LOOKBACK_DAYS = 365

    # Maks plausible snittfart (m/s) per vinduslengde — filtrerer GPS-spikes i effort/CS.
    _MAX_AVG_SPEED_MPS: Dict[int, float] = {
        30: 10.0,
        60: 9.5,
        180: 8.0,
        360: 7.8,
        300: 7.5,
        600: 7.2,
        720: 7.0,
        1200: 6.8,
        1800: 6.5,
        2400: 6.5,
        3600: 6.2,
    }
    _ABSOLUTE_SAMPLE_SPEED_CAP_MPS = 8.5

    def __init__(self, db: Session, storage: DataStorage):
        self.db = db
        self.storage = storage

    @property
    def _speed_duration_seconds(self) -> List[int]:
        """Alle varigheter vi rapporterer for fart (kurve + CS-tabell)."""
        return sorted(set(self.SPEED_CURVE_DURATIONS + self.CRITICAL_SPEED_DURATIONS))

    @property
    def critical_speed_pace_table_durations(self) -> List[int]:
        """Varigheter i pace-tabellen (CS-varigheter + 60 min)."""
        return sorted(set(self.CRITICAL_SPEED_DURATIONS + [3600]))

    def _normalize_speed_mps(
        self,
        speed: pd.Series,
        reference_speed_mps: Optional[float] = None,
    ) -> pd.Series:
        """Normaliserer FIT-fart til m/s. Eldre parquet kan ha km/t uten konvertering."""
        numeric = pd.to_numeric(speed, errors="coerce")
        positive = numeric[numeric > 0]
        if positive.empty:
            return numeric
        median = float(positive.median())
        if pd.notna(reference_speed_mps) and reference_speed_mps > 0:
            ratio = median / reference_speed_mps
            if 2.2 <= ratio <= 4.5:
                return numeric / 3.6
        if median > 8:
            return numeric / 3.6
        return numeric

    def _max_plausible_avg_speed(self, duration_s: int) -> float:
        if duration_s in self._MAX_AVG_SPEED_MPS:
            return self._MAX_AVG_SPEED_MPS[duration_s]
        keys = sorted(self._MAX_AVG_SPEED_MPS)
        if duration_s <= keys[0]:
            return self._MAX_AVG_SPEED_MPS[keys[0]]
        if duration_s >= keys[-1]:
            return self._MAX_AVG_SPEED_MPS[keys[-1]]
        for lo, hi in zip(keys, keys[1:]):
            if lo <= duration_s <= hi:
                span = hi - lo
                weight = (duration_s - lo) / span if span else 0.0
                return (
                    self._MAX_AVG_SPEED_MPS[lo] * (1 - weight)
                    + self._MAX_AVG_SPEED_MPS[hi] * weight
                )
        return self._ABSOLUTE_SAMPLE_SPEED_CAP_MPS

    def _clip_speed_samples(self, df: pd.DataFrame) -> pd.DataFrame:
        """Klipper enkelt-sample fart som er åpenbare GPS-spikes."""
        reasonable = df.loc[df["speed_mps"] >= 1.0, "speed_mps"]
        if len(reasonable) >= 5:
            median = float(reasonable.median())
            cap = min(self._ABSOLUTE_SAMPLE_SPEED_CAP_MPS, max(6.0, median * 2.5))
        else:
            cap = self._ABSOLUTE_SAMPLE_SPEED_CAP_MPS
        df = df.copy()
        df["speed_mps"] = df["speed_mps"].clip(upper=cap)
        return df

    def _is_plausible_speed_effort(self, effort: Dict[str, Any]) -> bool:
        duration_s = int(effort.get("duration_seconds") or 0)
        speed_mps = effort.get("speed_mps", effort.get("value"))
        if duration_s <= 0 or speed_mps is None:
            return False
        return float(speed_mps) <= self._max_plausible_avg_speed(duration_s)

    def _details_for_activity(self, activity: Activity) -> Optional[pd.DataFrame]:
        try:
            return self.storage.get_activity_details(int(activity.activity_id))
        except Exception:
            return None

    def _prepare_samples(
        self,
        details_df: pd.DataFrame,
        drop_warmup: bool = True,
        reference_speed_mps: Optional[float] = None,
    ) -> pd.DataFrame:
        if details_df is None or details_df.empty:
            return pd.DataFrame()
        if "timestamp" not in details_df.columns or "speed" not in details_df.columns:
            return pd.DataFrame()

        df = details_df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["speed_mps"] = self._normalize_speed_mps(df["speed"], reference_speed_mps)
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

        df = self._clip_speed_samples(df)

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

        if value_col == "speed_mps":
            speed_cap = self._max_plausible_avg_speed(duration_s)
            if best_value > speed_cap:
                return None

        return {
            "duration_seconds": duration_s,
            "value": best_value,
            "start_time": samples["timestamp"].iloc[best_start_idx].isoformat(),
            "end_time": samples["timestamp"].iloc[best_end_idx].isoformat(),
        }

    def extract_activity_best_efforts(self, activity: Activity) -> List[Dict[str, Any]]:
        details = self._details_for_activity(activity)
        ref_speed = float(activity.average_speed) if activity.average_speed else None
        samples = (
            self._prepare_samples(details, drop_warmup=True, reference_speed_mps=ref_speed)
            if details is not None
            else pd.DataFrame()
        )
        efforts: List[Dict[str, Any]] = []
        if samples.empty:
            return efforts

        durations = sorted(set(self.SPEED_CURVE_DURATIONS + self.CRITICAL_SPEED_DURATIONS))
        for duration_s in durations:
            speed_effort = self._best_average_for_duration(samples, duration_s, "speed_mps")
            if speed_effort and self._is_plausible_speed_effort(
                {"duration_seconds": duration_s, "speed_mps": speed_effort["value"]}
            ):
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
        if not is_running_activity(activity):
            return None

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
        ref_speed = float(activity.average_speed) if activity.average_speed else None
        samples = (
            self._prepare_samples(details, drop_warmup=True, reference_speed_mps=ref_speed)
            if details is not None
            else pd.DataFrame()
        )
        if samples.empty or len(samples) < 20:
            return None

        total_activity_s = float(activity.duration or 0)
        if details is not None and not details.empty and "timestamp" in details.columns:
            ts = pd.to_datetime(details["timestamp"], errors="coerce").dropna()
            if len(ts) >= 2:
                total_activity_s = max(total_activity_s, (ts.iloc[-1] - ts.iloc[0]).total_seconds())

        if total_activity_s < 45 * 60:
            return None

        duration = samples["elapsed_s"].iloc[-1] - samples["elapsed_s"].iloc[0]
        if duration < 30 * 60:
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

    def _running_activities(
        self,
        days: Optional[int] = None,
        *,
        include_treadmill: bool = False,
        end_date: Optional[date] = None,
    ) -> List[Activity]:
        end_dt = datetime.combine(end_date or date.today(), time.max).replace(tzinfo=timezone.utc)
        query = (
            self.db.query(Activity)
            .filter(Activity.start_time <= end_dt)
            .order_by(Activity.start_time.asc())
        )
        if days is not None:
            cutoff = end_dt - timedelta(days=days)
            query = query.filter(Activity.start_time >= cutoff)
        activities = query.all()
        return [
            activity
            for activity in activities
            if is_running_activity(activity, include_treadmill=include_treadmill)
        ]

    def _running_activities_for_calendar_year(
        self,
        year: int,
        *,
        include_treadmill: bool = False,
    ) -> List[Activity]:
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
        query = (
            self.db.query(Activity)
            .filter(Activity.start_time >= start, Activity.start_time < end)
            .order_by(Activity.start_time.asc())
        )
        return [
            activity
            for activity in query.all()
            if is_running_activity(activity, include_treadmill=include_treadmill)
        ]

    def collect_best_efforts(
        self,
        days: Optional[int] = None,
        *,
        include_treadmill: bool = False,
    ) -> List[Dict[str, Any]]:
        efforts: List[Dict[str, Any]] = []
        for activity in self._running_activities(days=days, include_treadmill=include_treadmill):
            efforts.extend(self.extract_activity_best_efforts(activity))
        return efforts

    def collect_best_efforts_for_calendar_year(
        self,
        year: int,
        *,
        include_treadmill: bool = False,
    ) -> List[Dict[str, Any]]:
        efforts: List[Dict[str, Any]] = []
        for activity in self._running_activities_for_calendar_year(
            year,
            include_treadmill=include_treadmill,
        ):
            efforts.extend(self.extract_activity_best_efforts(activity))
        return efforts

    def _build_duration_curve_from_efforts(
        self,
        efforts: List[Dict[str, Any]],
        *,
        days: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Dict[str, Any]:
        curves: Dict[str, List[Dict[str, Any]]] = {"speed": [], "power": []}
        for metric_type in curves:
            metric_efforts = [e for e in efforts if e.get("metric_type") == metric_type]
            duration_list = (
                self._speed_duration_seconds
                if metric_type == "speed"
                else self.SPEED_CURVE_DURATIONS
            )
            for duration_s in duration_list:
                candidates = [e for e in metric_efforts if e["duration_seconds"] == duration_s]
                if not candidates:
                    continue
                if metric_type == "speed":
                    candidates = [e for e in candidates if self._is_plausible_speed_effort(e)]
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
        result: Dict[str, Any] = {
            "days": days,
            "curves": curves,
            "effort_count": len(efforts),
        }
        if year is not None:
            result["year"] = year
        return result

    def build_duration_curve(
        self,
        days: Optional[int] = None,
        *,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        return self._build_duration_curve_from_efforts(
            self.collect_best_efforts(days=days, include_treadmill=include_treadmill),
            days=days,
        )

    def build_duration_curve_for_calendar_year(
        self,
        year: int,
        *,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        return self._build_duration_curve_from_efforts(
            self.collect_best_efforts_for_calendar_year(year, include_treadmill=include_treadmill),
            year=year,
        )

    def build_critical_speed_pace_by_year(
        self,
        years: int = 3,
        *,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        """
        Beste pace per CS-varighet og kalenderår.
        Manglende kortere varigheter fylles fra samme økt som beste lengre
        varighet det året (f.eks. 6/12 min fra løpet som ga 20 min).
        """
        current_year = datetime.now(timezone.utc).year
        target_years = [current_year - offset for offset in range(years - 1, -1, -1)]
        rows: List[Dict[str, Any]] = [
            {
                "duration_seconds": duration_s,
                "paces_by_year": {str(year): None for year in target_years},
            }
            for duration_s in self.critical_speed_pace_table_durations
        ]
        row_by_dur = {row["duration_seconds"]: row for row in rows}
        table_durations = set(self.critical_speed_pace_table_durations)

        for year in target_years:
            speed_efforts = [
                e
                for e in self.collect_best_efforts_for_calendar_year(
                    year,
                    include_treadmill=include_treadmill,
                )
                if e.get("metric_type") == "speed"
                and int(e["duration_seconds"]) in table_durations
                and self._is_plausible_speed_effort(e)
            ]
            best_by_dur: Dict[int, Dict[str, Any]] = {}
            for effort in speed_efforts:
                duration_s = int(effort["duration_seconds"])
                speed_mps = float(effort["speed_mps"])
                if duration_s not in best_by_dur or speed_mps > float(best_by_dur[duration_s]["speed_mps"]):
                    best_by_dur[duration_s] = effort

            anchor_effort = None
            for duration_s in sorted(self.critical_speed_pace_table_durations, reverse=True):
                if duration_s in best_by_dur:
                    anchor_effort = best_by_dur[duration_s]
                    break

            if anchor_effort:
                anchor_id = str(anchor_effort.get("activity_id"))
                activity = self.db.query(Activity).filter_by(activity_id=anchor_id).first()
                for duration_s in self.critical_speed_pace_table_durations:
                    if duration_s in best_by_dur:
                        continue
                    same_act = next(
                        (
                            e
                            for e in speed_efforts
                            if str(e.get("activity_id")) == anchor_id
                            and int(e["duration_seconds"]) == duration_s
                        ),
                        None,
                    )
                    if same_act is None and activity is not None:
                        for effort in self.extract_activity_best_efforts(activity):
                            if (
                                effort.get("metric_type") == "speed"
                                and int(effort["duration_seconds"]) == duration_s
                                and self._is_plausible_speed_effort(
                                    {
                                        "duration_seconds": duration_s,
                                        "speed_mps": effort.get("speed_mps", effort.get("value")),
                                    }
                                )
                            ):
                                same_act = effort
                                break
                    if same_act is not None:
                        best_by_dur[duration_s] = {**same_act, "_from_anchor": True}

            for duration_s, effort in best_by_dur.items():
                speed_mps = float(effort["speed_mps"])
                row_by_dur[duration_s]["paces_by_year"][str(year)] = {
                    "pace_sec_per_km": round(1000 / speed_mps, 1),
                    "speed_mps": round(speed_mps, 4),
                    "activity_id": effort.get("activity_id"),
                    "source": "anchor_activity" if effort.get("_from_anchor") else "year_best",
                }

        return {
            "years": target_years,
            "rows": rows,
            "include_treadmill": include_treadmill,
        }

    def build_duration_curve_year_comparison(
        self,
        years: int = 3,
        *,
        include_treadmill: bool = False,
    ) -> List[Dict[str, Any]]:
        current_year = datetime.now(timezone.utc).year
        target_years = [current_year - offset for offset in range(years - 1, -1, -1)]
        return [
            {
                "year": year,
                **self.build_duration_curve_for_calendar_year(
                    year,
                    include_treadmill=include_treadmill,
                ),
            }
            for year in target_years
        ]

    def calculate_critical_speed(
        self,
        days: Optional[int] = CRITICAL_SPEED_LOOKBACK_DAYS,
        *,
        include_treadmill: bool = False,
    ) -> Dict[str, Any]:
        efforts = self.collect_best_efforts(days=days, include_treadmill=include_treadmill)
        speed_efforts = [e for e in efforts if e.get("metric_type") == "speed"]
        best_by_duration: Dict[int, Dict[str, Any]] = {}
        for duration_s in self.CRITICAL_SPEED_DURATIONS:
            candidates = [
                e for e in speed_efforts
                if e["duration_seconds"] == duration_s and self._is_plausible_speed_effort(e)
            ]
            if candidates:
                best = max(candidates, key=lambda e: e["speed_mps"])
                speed_mps = float(best["speed_mps"])
                best["pace_sec_per_km"] = (
                    round(1000 / speed_mps, 1) if speed_mps > 0 else None
                )
                best_by_duration[duration_s] = best

        if len(best_by_duration) < 3:
            return {
                "critical_speed_mps": None,
                "critical_pace_sec_per_km": None,
                "d_prime": None,
                "model_r2": None,
                "model_quality": "insufficient_data",
                "efforts": list(best_by_duration.values()),
                "include_treadmill": include_treadmill,
                "lookback_days": days,
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
            "include_treadmill": include_treadmill,
            "lookback_days": days,
        }

    def resolve_critical_speed_payload(
        self,
        payload: Optional[Dict[str, Any]],
        *,
        include_treadmill: bool = False,
        days: int = CRITICAL_SPEED_LOOKBACK_DAYS,
    ) -> Dict[str, Any]:
        """Henter CS-variant fra snapshot (utendørs / med tredemølle), ellers beregner på nytt."""
        def fresh() -> Dict[str, Any]:
            return self.calculate_critical_speed(days=days, include_treadmill=include_treadmill)

        if not payload:
            return fresh()

        if payload.get("outdoor") is not None or payload.get("with_treadmill") is not None:
            key = "with_treadmill" if include_treadmill else "outdoor"
            variant = payload.get(key)
            if variant and variant.get("lookback_days") == days:
                resolved = dict(variant)
                resolved["calculated_at"] = payload.get("calculated_at")
                resolved["data_quality_score"] = payload.get("data_quality_score")
                resolved["model_quality"] = variant.get("model_quality") or payload.get("model_quality")
                return resolved
            return fresh()

        if payload.get("lookback_days") == days and payload.get("critical_speed_mps") is not None:
            legacy = dict(payload)
            legacy.setdefault("include_treadmill", False)
            return legacy

        return fresh()

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
        critical_speed = {
            "outdoor": self.calculate_critical_speed(
                days=self.CRITICAL_SPEED_LOOKBACK_DAYS,
                include_treadmill=False,
            ),
            "with_treadmill": self.calculate_critical_speed(
                days=self.CRITICAL_SPEED_LOOKBACK_DAYS,
                include_treadmill=True,
            ),
        }
        curve_all = self.build_duration_curve(days=None)
        curve_90 = self.build_duration_curve(days=90)
        curve_365 = self.build_duration_curve(days=365)
        current_year = datetime.now(timezone.utc).year
        by_year = {
            str(year): self.build_duration_curve_for_calendar_year(year, include_treadmill=False)
            for year in range(current_year - 2, current_year + 1)
        }
        by_year_with_treadmill = {
            str(year): self.build_duration_curve_for_calendar_year(year, include_treadmill=True)
            for year in range(current_year - 2, current_year + 1)
        }
        duration_curve = {
            "all_time": curve_all,
            "last_90_days": curve_90,
            "last_365_days": curve_365,
            "by_year": by_year,
            "by_year_with_treadmill": by_year_with_treadmill,
        }

        outdoor_cs = critical_speed["outdoor"]
        self._upsert_snapshot(
            "critical_speed",
            critical_speed,
            data_quality_score=100.0 if outdoor_cs.get("critical_speed_mps") else 0.0,
            model_quality=outdoor_cs.get("model_quality"),
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
