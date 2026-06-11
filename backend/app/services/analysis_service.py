import pandas as pd
import numpy as np
import logging
import re
import json
from fastapi import HTTPException
from ..storage import DataStorage
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from ..database.models import Activity
from .hrv_service import HRVService
from .body_battery_service import BodyBatteryService
from ..utils.activity_filters import is_running_activity
from ..utils.grade_adjusted_pace import compute_avg_grade_adjusted_speed_mps

logger = logging.getLogger(__name__)

_MIN_DERIVED_SPEED_SAMPLES = 20


def enrich_fit_speed_from_distance(details_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fyll manglende FIT-speed fra distance/timestamp når speed-kolonnen er tom.
    Vanlig på tredemølle der distance finnes men enhanced_speed mangler i parquet.
    """
    if details_df is None or details_df.empty:
        return details_df

    df = details_df.copy()
    if "speed" not in df.columns:
        df["speed"] = np.nan

    speed = pd.to_numeric(df["speed"], errors="coerce")
    if int((speed > 0).sum()) >= _MIN_DERIVED_SPEED_SAMPLES:
        return df

    if "distance" not in df.columns or "timestamp" not in df.columns:
        return df

    work = df.sort_values("timestamp").copy()
    dist = pd.to_numeric(work["distance"], errors="coerce")
    ts = pd.to_datetime(work["timestamp"], errors="coerce")
    if int(dist.notna().sum()) < _MIN_DERIVED_SPEED_SAMPLES:
        return df

    dt = ts.diff().dt.total_seconds()
    derived = dist.diff() / dt
    valid = (
        derived.notna()
        & (dt > 0)
        & (dt <= 30)
        & (derived > 0)
        & (derived < 12)
    )
    current_speed = pd.to_numeric(work["speed"], errors="coerce")
    missing = current_speed.isna() | (current_speed <= 0)
    fill = missing & valid
    if not fill.any():
        return df

    work.loc[fill, "speed"] = derived[fill]
    return work.sort_index()


class AnalysisService:
    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.hrv_service = HRVService(storage)
        self.body_battery_service = None  # Vil bli initialisert når nødvendig

    @staticmethod
    def _maybe_commit(db: Session, *, persist: bool) -> None:
        """Commit kun når kaller ber om det (batch-orkestrering samler én commit)."""
        if persist:
            db.commit()

    def _to_float(self, value: Any) -> Optional[float]:
        """Konverterer ulike numeriske representasjoner til float."""
        if isinstance(value, dict):
            # Noen kilder kan pakke tall inn i {"value": ...}
            nested_value = value.get("value")
            if nested_value is not None:
                return self._to_float(nested_value)
            return None
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r'[-+]?(?:\d*\.\d+|\d+)', value)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
        return None

    def _coerce_dict(self, value: Any) -> Optional[Dict[str, Any]]:
        """Normaliserer JSON-felt til dict når mulig."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                loaded = json.loads(text)
            except Exception:
                return None
            return loaded if isinstance(loaded, dict) else None
        return None

    def _extract_records(self, details: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """Henter records-liste fra kjente JSON-shapes."""
        candidate_lists = [
            details.get("records"),
            details.get("fit_records"),
            details.get("samples"),
        ]
        nested_containers = [
            details.get("fit_data"),
            details.get("details"),
            details.get("activity_details"),
            details.get("metrics"),
        ]
        for container in nested_containers:
            if isinstance(container, dict):
                candidate_lists.extend([
                    container.get("records"),
                    container.get("fit_records"),
                    container.get("samples"),
                ])
        for candidate in candidate_lists:
            if isinstance(candidate, list):
                return candidate
        return None

    def _get_fit_details_for_activity(self, activity_id: int, activity: Activity) -> Optional[pd.DataFrame]:
        """
        Hent FIT-detaljer fra parquet først, med fallback til detailed_metrics i DB.
        Returnerer DataFrame med minst timestamp/speed/heart_rate når tilgjengelig.
        """
        # 1) Primærkilde: parquet-lager
        details_df = self.storage.get_activity_details(activity_id)
        if details_df is not None and not details_df.empty:
            return enrich_fit_speed_from_distance(details_df)

        # 2) Fallback: detailed_metrics JSON lagret på aktivitet
        details = activity.detailed_metrics if activity else None
        details = self._coerce_dict(details)
        if not details:
            return None

        records = self._extract_records(details)
        if not records:
            return None

        parsed_records: List[Dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            timestamp = pd.to_datetime(
                record.get("timestamp")
                or record.get("time")
                or record.get("record_timestamp"),
                errors="coerce",
            )
            if pd.isna(timestamp):
                continue
            speed = self._to_float(
                record.get("enhanced_speed")
                or record.get("speed")
                or record.get("enhancedSpeed")
            )
            heart_rate = self._to_float(
                record.get("heart_rate")
                or record.get("heartrate")
                or record.get("hr")
            )
            distance = self._to_float(
                record.get("distance")
                or record.get("enhanced_distance")
                or record.get("enhancedDistance")
            )
            altitude = self._to_float(
                record.get("altitude")
                or record.get("enhanced_altitude")
                or record.get("enhancedAltitude")
            )
            parsed_records.append({
                "timestamp": timestamp,
                "speed": speed,
                "heart_rate": heart_rate,
                "distance": distance,
                "altitude": altitude,
            })

        if not parsed_records:
            return None

        return enrich_fit_speed_from_distance(pd.DataFrame(parsed_records))

    def _split_activity_halves(self, valid_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, str]:
        """
        Del aktivitet i to halvdeler etter distanse (foretrukket) eller tid — ikke sample-telling.
        """
        ordered = valid_data.sort_values("timestamp").copy()
        if len(ordered) < 2:
            return ordered.iloc[0:0], ordered.iloc[0:0], "time"

        if "distance" in ordered.columns:
            distance = pd.to_numeric(ordered["distance"], errors="coerce")
            if int(distance.notna().sum()) >= _MIN_DERIVED_SPEED_SAMPLES:
                start_dist = float(distance.min())
                end_dist = float(distance.max())
                total_distance = end_dist - start_dist
                if total_distance >= 200:
                    half_distance = start_dist + total_distance / 2
                    first_half = ordered[distance <= half_distance]
                    second_half = ordered[distance > half_distance]
                    if len(first_half) >= 10 and len(second_half) >= 10:
                        return first_half, second_half, "distance"

        start = ordered["timestamp"].iloc[0]
        end = ordered["timestamp"].iloc[-1]
        midpoint_time = start + (end - start) / 2
        first_half = ordered[ordered["timestamp"] < midpoint_time]
        second_half = ordered[ordered["timestamp"] >= midpoint_time]
        return first_half, second_half, "time"

    def _half_pace_min_per_km(self, half: pd.DataFrame) -> Optional[float]:
        """Pace (min/km) for en halvdel basert på tid/distanse når mulig."""
        if len(half) < 2:
            return None

        ordered = half.sort_values("timestamp")
        duration_sec = (ordered["timestamp"].iloc[-1] - ordered["timestamp"].iloc[0]).total_seconds()
        if duration_sec <= 0:
            return None

        if "distance" in ordered.columns:
            distance = pd.to_numeric(ordered["distance"], errors="coerce").dropna()
            if len(distance) >= 2:
                distance_m = float(distance.iloc[-1] - distance.iloc[0])
                if distance_m >= 50:
                    return (duration_sec / distance_m) * 1000 / 60

        mean_speed = float(ordered["speed"].mean())
        if mean_speed <= 0:
            return None
        return 1000 / (mean_speed * 60)

    def calculate_negative_split(
        self,
        activity_id: int,
        db: Session,
        *,
        persist: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Beregner negativ split for en aktivitet basert på FIT-data.
        Negativ split = (andre halvdel pace - første halvdel pace) / første halvdel pace * 100
        Negativ verdi = negativ split (raskere andre halvdel)
        Positiv verdi = positiv split (saktere andre halvdel)
        """
        try:
            # Hent aktivitet fra database
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                logger.warning(f"Aktivitet {activity_id} ikke funnet i database")
                return None
            
            # Hvis allerede beregnet, returner cached verdi
            if activity.negative_split_percent is not None:
                return {
                    "activity_id": activity_id,
                    "negative_split_percent": round(activity.negative_split_percent, 2),
                    "calculation_method": "cached"
                }
            
            # Hent FIT-data (parquet først, deretter DB fallback)
            details_df = self._get_fit_details_for_activity(activity_id, activity)
            if details_df is None or details_df.empty:
                logger.warning(f"Ingen FIT-data tilgjengelig for aktivitet {activity_id}")
                raise HTTPException(status_code=404, detail="No FIT data available for this activity")
            
            # Sjekk at vi har nødvendige kolonner
            required_columns = ['speed', 'timestamp']
            if not all(col in details_df.columns for col in required_columns):
                logger.warning(f"Mangler nødvendige kolonner for negative split: {required_columns}")
                raise HTTPException(status_code=404, detail="Missing required data columns for negative split calculation")
            
            # Filtrer ut rader med gyldig speed og timestamp data
            valid_data = details_df.copy()
            valid_data["speed"] = self._normalize_speed_mps(valid_data["speed"])
            valid_data = valid_data.dropna(subset=["speed", "timestamp"])
            valid_data = valid_data[valid_data["speed"] > 0]
            
            if len(valid_data) < 20:
                logger.warning(f"Ikke nok datapunkter for negative split beregning: {len(valid_data)}")
                raise HTTPException(status_code=404, detail="Insufficient data points for negative split calculation")
            
            valid_data = valid_data.sort_values("timestamp")
            first_half, second_half, split_method = self._split_activity_halves(valid_data)

            if len(first_half) < 10 or len(second_half) < 10:
                logger.warning(
                    "Ikke nok datapunkter per halvdel for negative split: %s/%s",
                    len(first_half),
                    len(second_half),
                )
                raise HTTPException(
                    status_code=404,
                    detail="Insufficient split data for negative split calculation",
                )

            first_half_pace = self._half_pace_min_per_km(first_half)
            second_half_pace = self._half_pace_min_per_km(second_half)

            if not first_half_pace or first_half_pace <= 0 or not second_half_pace:
                logger.warning(
                    "Ugyldig pace for negative split: first=%s second=%s",
                    first_half_pace,
                    second_half_pace,
                )
                return None

            negative_split_percent = ((second_half_pace - first_half_pace) / first_half_pace) * 100

            activity.negative_split_percent = negative_split_percent
            self._maybe_commit(db, persist=persist)

            logger.info(
                "Beregnet negative split for aktivitet %s: %.2f%% (split=%s)",
                activity_id,
                negative_split_percent,
                split_method,
            )

            return {
                "activity_id": activity_id,
                "negative_split_percent": round(negative_split_percent, 2),
                "calculation_method": "calculated",
                "first_half_pace": round(first_half_pace, 2),
                "second_half_pace": round(second_half_pace, 2),
                "data_points": len(valid_data),
                "split_method": split_method,
            }
            
        except HTTPException:
            # Re-raise HTTPExceptions without logging them as errors
            raise
        except Exception as e:
            logger.error(f"Feil ved beregning av negative split for aktivitet {activity_id}: {e}")
            return None

    def calculate_grade_adjusted_speed(
        self,
        activity_id: int,
        db: Session,
        *,
        overwrite: bool = False,
        persist: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Beregner grade-adjusted speed (m/s) fra FIT når Garmin ikke leverer avgGradeAdjustedSpeed.
        """
        try:
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                logger.warning("Aktivitet %s ikke funnet i database", activity_id)
                return None

            if not is_running_activity(activity, include_treadmill=True):
                return None

            if activity.avg_grade_adjusted_speed is not None and not overwrite:
                pace_sec = 1000.0 / activity.avg_grade_adjusted_speed
                return {
                    "activity_id": activity_id,
                    "avg_grade_adjusted_speed": round(activity.avg_grade_adjusted_speed, 4),
                    "grade_adjusted_pace_sec_per_km": round(pace_sec, 1),
                    "calculation_method": "stored",
                }

            details_df = self._get_fit_details_for_activity(activity_id, activity)
            if details_df is None or details_df.empty:
                return None

            ref_speed = None
            if activity.average_moving_speed and activity.average_moving_speed > 0:
                ref_speed = float(activity.average_moving_speed)
            elif activity.average_speed and activity.average_speed > 0:
                ref_speed = float(activity.average_speed)

            result = compute_avg_grade_adjusted_speed_mps(
                details_df,
                reference_speed_mps=ref_speed,
            )
            if result is None:
                return None

            activity.avg_grade_adjusted_speed = result.speed_mps
            self._maybe_commit(db, persist=persist)

            pace_sec = 1000.0 / result.speed_mps
            logger.info(
                "Beregnet grade-adjusted speed for aktivitet %s: %.4f m/s (%s samples)",
                activity_id,
                result.speed_mps,
                result.sample_count,
            )
            return {
                "activity_id": activity_id,
                "avg_grade_adjusted_speed": result.speed_mps,
                "grade_adjusted_pace_sec_per_km": round(pace_sec, 1),
                "calculation_method": result.method,
                "sample_count": result.sample_count,
            }
        except Exception as exc:
            logger.error("Feil ved beregning av grade-adjusted speed for aktivitet %s: %s", activity_id, exc)
            return None

    def calculate_decoupling(self, activity_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Beregner cardiac-aerobic decoupling for en aktivitet basert på FIT-data.
        Bruker forbedret Efficiency Factor-basert beregning.
        """
        result = self.calculate_efficiency_metrics(activity_id, db)
        if result is None:
            return None
        return {
            "activity_id": activity_id,
            "decoupling_percent": result["aerobic_decoupling_percent"],
            "calculation_method": result["calculation_method"],
            "first_half_hr": result["first_half_heart_rate"],
            "first_half_speed": result["first_half_speed_mps"],
            "second_half_hr": result["second_half_heart_rate"],
            "second_half_speed": result["second_half_speed_mps"],
            "first_half_efficiency_factor": result["first_half_efficiency_factor"],
            "second_half_efficiency_factor": result["second_half_efficiency_factor"],
            "efficiency_factor": result["efficiency_factor"],
            "sample_count": result["sample_count"],
        }

    def _normalize_speed_mps(self, speed: pd.Series) -> pd.Series:
        """Normaliserer FIT speed til m/s. Noen eldre data ligger som km/t."""
        numeric_speed = pd.to_numeric(speed, errors="coerce")
        median_speed = numeric_speed[(numeric_speed > 0)].median()
        if pd.notna(median_speed) and median_speed > 8:
            return numeric_speed / 3.6
        return numeric_speed

    def _prepare_aerobic_metric_samples(self, details_df: pd.DataFrame) -> pd.DataFrame:
        """Filtrerer samples for EF/decoupling: warmup, stopp, manglende puls, lav fart."""
        prepared = details_df.copy()
        prepared["timestamp"] = pd.to_datetime(prepared["timestamp"], errors="coerce")
        prepared["heart_rate"] = pd.to_numeric(prepared["heart_rate"], errors="coerce")
        prepared["speed_mps"] = self._normalize_speed_mps(prepared["speed"])
        prepared = prepared.dropna(subset=["timestamp"])
        prepared = prepared.sort_values("timestamp")
        prepared = prepared.drop_duplicates(subset=["timestamp"], keep="last")
        if prepared.empty:
            return prepared

        start = prepared["timestamp"].iloc[0]
        end = prepared["timestamp"].iloc[-1]
        total_seconds = (end - start).total_seconds()
        if total_seconds <= 0:
            return prepared.iloc[0:0].copy()

        # Dropp første 10 minutter (warmup)
        if total_seconds > 600:
            prepared = prepared[prepared["timestamp"] >= start + pd.Timedelta(seconds=600)]

        # Stopp/pauser, manglende puls, svært lav fart, åpenbare pulsfeil
        prepared = prepared.dropna(subset=["heart_rate", "speed_mps"])
        prepared = prepared[
            (prepared["heart_rate"].between(40, 220))
            & (prepared["speed_mps"] >= 1.0)
        ]
        if len(prepared) >= 5:
            hr_median = prepared["heart_rate"].rolling(5, center=True, min_periods=3).median()
            hr_spike = (prepared["heart_rate"] - hr_median).abs() > 35
            prepared = prepared[~hr_spike.fillna(False)]

        return prepared.sort_values("timestamp")

    def _per_sample_efficiency_factor(self, samples: pd.DataFrame) -> pd.Series:
        ef = samples["speed_mps"] / samples["heart_rate"]
        return ef.replace([np.inf, -np.inf], np.nan).dropna()

    def _efficiency_factor(self, samples: pd.DataFrame) -> Optional[float]:
        """Gjennomsnitt av per-sample EF = speed_mps / heart_rate."""
        ef_values = self._per_sample_efficiency_factor(samples)
        if ef_values.empty:
            return None
        return float(ef_values.mean())

    def _median_efficiency_factor(self, samples: pd.DataFrame) -> Optional[float]:
        ef_values = self._per_sample_efficiency_factor(samples)
        if ef_values.empty:
            return None
        return float(ef_values.median())

    def _steady_state_efficiency_factor(self, samples: pd.DataFrame) -> Optional[float]:
        """EF på jevne fartssamples (±10 % av medianfart)."""
        if len(samples) < 8:
            return None
        median_speed = samples["speed_mps"].median()
        if pd.isna(median_speed) or median_speed <= 0:
            return None
        steady = samples[
            samples["speed_mps"].between(median_speed * 0.90, median_speed * 1.10)
        ]
        if len(steady) < 8:
            return None
        ef_values = self._per_sample_efficiency_factor(steady)
        if ef_values.empty:
            return None
        return float(ef_values.mean())

    def _compute_efficiency_data_quality(
        self,
        raw_df: pd.DataFrame,
        valid_df: pd.DataFrame,
    ) -> float:
        """Score 0–100 for datadekning etter filtrering."""
        if raw_df.empty:
            return 0.0
        total = len(raw_df)
        with_hr = raw_df["heart_rate"].notna().sum() if "heart_rate" in raw_df.columns else 0
        retained = len(valid_df) / total if total else 0.0
        hr_coverage = with_hr / total if total else 0.0
        duration_score = min(
            1.0,
            (
                (valid_df["timestamp"].iloc[-1] - valid_df["timestamp"].iloc[0]).total_seconds()
                / 2400
            )
            if len(valid_df) >= 2
            else 0.0,
        )
        score = (retained * 0.4 + hr_coverage * 0.3 + duration_score * 0.3) * 100
        return round(min(100.0, max(0.0, score)), 1)

    def _assess_decoupling_suitability(
        self,
        raw_df: pd.DataFrame,
        valid_df: pd.DataFrame,
        activity: Activity,
    ) -> Dict[str, Any]:
        """Vurderer om aktiviteten egner seg for aerobic decoupling."""
        reasons: List[str] = []
        total_seconds = 0.0
        if not raw_df.empty and "timestamp" in raw_df.columns:
            ts = pd.to_datetime(raw_df["timestamp"], errors="coerce").dropna()
            if len(ts) >= 2:
                total_seconds = (ts.iloc[-1] - ts.iloc[0]).total_seconds()

        valid_seconds = 0.0
        if len(valid_df) >= 2:
            valid_seconds = (valid_df["timestamp"].iloc[-1] - valid_df["timestamp"].iloc[0]).total_seconds()

        if total_seconds < 45 * 60 and valid_seconds < 40 * 60:
            reasons.append("too_short")

        if not raw_df.empty and "speed_mps" not in raw_df.columns:
            raw_df = raw_df.copy()
            raw_df["speed_mps"] = self._normalize_speed_mps(raw_df.get("speed", pd.Series(dtype=float)))

        if len(raw_df) > 0:
            stop_ratio = (raw_df["speed_mps"].fillna(0) < 0.5).mean()
            if stop_ratio > 0.20:
                reasons.append("too_many_stops")

            hr_missing_ratio = raw_df["heart_rate"].isna().mean() if "heart_rate" in raw_df.columns else 1.0
            if hr_missing_ratio > 0.25:
                reasons.append("missing_heart_rate")

        if len(valid_df) >= 10:
            speed_cv = valid_df["speed_mps"].std() / valid_df["speed_mps"].mean()
            if pd.notna(speed_cv) and speed_cv > 0.20:
                reasons.append("interval_like_pace")

        distance_km = (activity.distance or 0) / 1000
        ascent = activity.total_ascent or 0
        if distance_km > 0 and ascent / distance_km > 30:
            reasons.append("very_hilly")

        quality_score = self._compute_efficiency_data_quality(raw_df, valid_df)
        if len(valid_df) < 20:
            reasons.append("insufficient_samples")

        suitable = len(reasons) == 0
        return {
            "decoupling_suitability_flag": "suitable" if suitable else "unsuitable",
            "decoupling_reason_if_unsuitable": ",".join(reasons) if reasons else None,
            "decoupling_data_quality_score": quality_score,
        }

    def calculate_efficiency_metrics(
        self,
        activity_id: int,
        db: Session,
        force_recalculate: bool = False,
        *,
        persist: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Beregner Efficiency Factor og Aerobic Decoupling fra FIT-data.

        Per-sample EF = speed_mps / heart_rate.
        Aerobic Decoupling = ((EF_first - EF_second) / EF_first) * 100.
        Positiv verdi betyr at effektiviteten faller i andre halvdel.
        """
        try:
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                logger.warning(f"Aktivitet {activity_id} ikke funnet i database")
                return None

            details_df = self._get_fit_details_for_activity(activity_id, activity)
            if details_df is None or details_df.empty:
                logger.warning(f"Ingen FIT-data tilgjengelig for aktivitet {activity_id}")
                raise HTTPException(status_code=404, detail="No FIT data available for this activity")

            required_columns = ['heart_rate', 'speed', 'timestamp']
            if not all(col in details_df.columns for col in required_columns):
                logger.warning(f"Mangler nødvendige kolonner for efficiency metrics: {required_columns}")
                raise HTTPException(status_code=404, detail="Missing required data columns for efficiency metrics calculation")

            raw_df = details_df.copy()
            raw_df["speed_mps"] = self._normalize_speed_mps(raw_df["speed"])

            valid_data = self._prepare_aerobic_metric_samples(details_df)
            if len(valid_data) < 16:
                logger.warning(f"Ikke nok datapunkter for efficiency metrics: {len(valid_data)}")
                raise HTTPException(status_code=404, detail="Insufficient data points for efficiency metrics calculation")

            midpoint_time = valid_data["timestamp"].iloc[0] + (
                valid_data["timestamp"].iloc[-1] - valid_data["timestamp"].iloc[0]
            ) / 2
            first_half = valid_data[valid_data["timestamp"] < midpoint_time]
            second_half = valid_data[valid_data["timestamp"] >= midpoint_time]

            if len(first_half) < 8 or len(second_half) < 8:
                logger.warning(
                    "Ikke nok datapunkter per halvdel for efficiency metrics: %s/%s",
                    len(first_half),
                    len(second_half),
                )
                raise HTTPException(status_code=404, detail="Insufficient split data for efficiency metrics calculation")

            first_half_ef = self._efficiency_factor(first_half)
            second_half_ef = self._efficiency_factor(second_half)
            overall_ef = self._efficiency_factor(valid_data)
            median_ef = self._median_efficiency_factor(valid_data)
            steady_ef = self._steady_state_efficiency_factor(valid_data)
            if not first_half_ef or not second_half_ef or not overall_ef:
                logger.warning("Ugyldig data for efficiency metrics beregning")
                return None

            decoupling_percent = ((first_half_ef - second_half_ef) / first_half_ef) * 100
            efficiency_data_quality = self._compute_efficiency_data_quality(raw_df, valid_data)
            suitability = self._assess_decoupling_suitability(raw_df, valid_data, activity)

            calculation_method = "calculated"
            if (
                not force_recalculate
                and activity.avg_efficiency_factor is not None
                and activity.decoupling_percent is not None
                and abs(activity.decoupling_percent - decoupling_percent) < 0.005
            ):
                calculation_method = "cached"
            else:
                activity.avg_efficiency_factor = round(overall_ef, 6)
                activity.median_efficiency_factor = round(median_ef, 6) if median_ef is not None else None
                activity.steady_state_efficiency_factor = (
                    round(steady_ef, 6) if steady_ef is not None else None
                )
                activity.efficiency_data_quality = efficiency_data_quality
                activity.decoupling_percent = round(decoupling_percent, 4)
                activity.decoupling_suitability_flag = suitability["decoupling_suitability_flag"]
                activity.decoupling_reason_if_unsuitable = suitability["decoupling_reason_if_unsuitable"]
                activity.decoupling_data_quality_score = suitability["decoupling_data_quality_score"]
                self._maybe_commit(db, persist=persist)

            first_half_hr = first_half["heart_rate"].mean()
            first_half_speed = first_half["speed_mps"].mean()
            second_half_hr = second_half["heart_rate"].mean()
            second_half_speed = second_half["speed_mps"].mean()

            logger.info(
                "Beregnet efficiency metrics for aktivitet %s: EF %.5f, decoupling %.2f%%",
                activity_id,
                overall_ef,
                decoupling_percent,
            )

            return self._build_efficiency_metrics_response(
                activity_id,
                activity,
                calculation_method,
                extra={
                    "first_half_efficiency_factor": round(first_half_ef, 5),
                    "second_half_efficiency_factor": round(second_half_ef, 5),
                    "first_half_heart_rate": round(first_half_hr, 1),
                    "second_half_heart_rate": round(second_half_hr, 1),
                    "first_half_speed_mps": round(first_half_speed, 2),
                    "second_half_speed_mps": round(second_half_speed, 2),
                    "sample_count": len(valid_data),
                    "first_half_sample_count": len(first_half),
                    "second_half_sample_count": len(second_half),
                },
                computed={
                    "efficiency_factor": round(overall_ef, 5),
                    "avg_efficiency_factor": round(overall_ef, 6),
                    "median_efficiency_factor": round(median_ef, 6) if median_ef is not None else None,
                    "steady_state_efficiency_factor": round(steady_ef, 6) if steady_ef is not None else None,
                    "efficiency_data_quality": efficiency_data_quality,
                    "aerobic_decoupling_percent": round(decoupling_percent, 2),
                    "decoupling_percent": round(decoupling_percent, 2),
                    "decoupling_suitability_flag": suitability["decoupling_suitability_flag"],
                    "decoupling_reason_if_unsuitable": suitability["decoupling_reason_if_unsuitable"],
                    "decoupling_data_quality_score": suitability["decoupling_data_quality_score"],
                },
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Feil ved beregning av efficiency metrics for aktivitet {activity_id}: {e}")
            return None

    def _build_efficiency_metrics_response(
        self,
        activity_id: int,
        activity: Activity,
        calculation_method: str,
        extra: Optional[Dict[str, Any]] = None,
        computed: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        values = computed or {
            "efficiency_factor": round(activity.avg_efficiency_factor or 0.0, 5),
            "avg_efficiency_factor": activity.avg_efficiency_factor,
            "median_efficiency_factor": activity.median_efficiency_factor,
            "steady_state_efficiency_factor": activity.steady_state_efficiency_factor,
            "efficiency_data_quality": activity.efficiency_data_quality,
            "aerobic_decoupling_percent": round(activity.decoupling_percent or 0.0, 2),
            "decoupling_percent": round(activity.decoupling_percent or 0.0, 2),
            "decoupling_suitability_flag": activity.decoupling_suitability_flag,
            "decoupling_reason_if_unsuitable": activity.decoupling_reason_if_unsuitable,
            "decoupling_data_quality_score": activity.decoupling_data_quality_score,
        }
        response: Dict[str, Any] = {
            "activity_id": activity_id,
            "efficiency_factor_unit": "m_per_s_per_bpm",
            "calculation_method": calculation_method,
            **values,
        }
        if extra:
            response.update(extra)
        return response

    def get_running_economy(self, activity_id: int) -> dict:
        """Beregner løpsøkonomi for en gitt aktivitet."""
        details_df = self.storage.activity_details
        activity_details = details_df[details_df['activity_id'] == activity_id]

        if activity_details.empty:
            return {"error": "Aktivitetsdetaljer ikke funnet"}

        # Eksempel på beregning (forenklet)
        # Løpsøkonomi = O2-forbruk (ml/kg/min) / hastighet (m/min)
        # Her bruker vi puls/hastighet som en proxy
        
        # Filtrer for å unngå deling på null
        activity_details = activity_details[activity_details['speed'] > 0]
        if activity_details.empty:
            return {"error": "Ingen bevegelsesdata i aktiviteten"}

        activity_details['heart_rate_per_speed'] = activity_details['heart_rate'] / activity_details['speed']
        
        avg_economy = activity_details['heart_rate_per_speed'].mean()
        
        # Erstatt NaN-verdier med None for JSON-kompatibilitet
        economy_data = activity_details[['timestamp', 'heart_rate_per_speed']].replace({np.nan: None})
        
        # Konverter datetime-kolonner til strenger for JSON-serialisering
        if 'timestamp' in economy_data.columns:
            economy_data['timestamp'] = economy_data['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        return {
            "activity_id": activity_id,
            "average_economy": avg_economy if pd.notna(avg_economy) else None,
            "economy_timeseries": economy_data.to_dict(orient='records')
        }

    def get_training_load(self) -> dict:
        """Beregner ukentlig Training Stress Score (TSS)."""
        activities_df = self.storage.activities
        if activities_df.empty:
            return {"weekly_tss": [], "avg_weekly_tss": 0}

        # Sørg for at 'start_time' er datetime
        activities_df['start_time'] = pd.to_datetime(activities_df['start_time'])
        
        # Beregn en forenklet TSS (dette er ikke en nøyaktig formel)
        activities_df['tss'] = activities_df['duration'] / 60 * (activities_df['average_hr'] / 150) ** 2
        
        # Grupper etter uke
        weekly_tss = activities_df.set_index('start_time').resample('W-Mon', label='left', closed='left')['tss'].sum().reset_index()
        weekly_tss.rename(columns={'start_time': 'week', 'tss': 'total_tss'}, inplace=True)
        
        avg_weekly_tss = weekly_tss['total_tss'].mean()

        if weekly_tss.empty:
            return {"weekly_tss": [], "avg_weekly_tss": 0}

        # Konverter til liste av dictionaries for JSON-respons
        # Erstatt NaN-verdier med None for JSON-kompatibilitet
        tss_clean = weekly_tss.replace({np.nan: None})
        
        # Konverter datetime-kolonner til strenger for JSON-serialisering
        if 'week' in tss_clean.columns:
            tss_clean['week'] = tss_clean['week'].dt.strftime('%Y-%m-%d')
        
        tss_list = tss_clean.to_dict(orient='records')
        
        return {
            "weekly_tss": tss_list,
            "avg_weekly_tss": avg_weekly_tss if pd.notna(avg_weekly_tss) else None
        }

    def get_hrv_for_activity_date(self, activity_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """Henter HRV-data for datoen en spesifikk aktivitet ble utført."""
        try:
            # Bruk HRVService for å hente data fra databasen
            return self.hrv_service.get_hrv_for_activity_date(activity_id, db)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Feil ved henting av HRV-data for aktivitet {activity_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    def get_hrv_over_time(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> dict:
        """Henter HRV-data over tid med valgfri datofiltrering."""
        try:
            # Bruk HRVService for å hente data fra databasen
            # Vi trenger en database session, så vi må håndtere dette annerledes
            # For nå, fallback til parquet-filer hvis database ikke er tilgjengelig
            hrv_df = self.storage.get_hrv_data()
            
            if hrv_df is None or hrv_df.empty:
                return {"hrv_data": [], "message": "Ingen HRV-data tilgjengelig"}
            
            # Filtrer på dato (indeks) hvis spesifisert
            if start_date:
                start_dt = pd.to_datetime(start_date).tz_localize(hrv_df.index.tz)
                hrv_df = hrv_df[hrv_df.index >= start_dt]
            
            if end_date:
                end_dt = pd.to_datetime(end_date).tz_localize(hrv_df.index.tz)
                hrv_df = hrv_df[hrv_df.index <= end_dt]
            
            # Sorter etter dato (indeks)
            hrv_df.sort_index(inplace=True)
            
            # Beregn 7-dagers glidende gjennomsnitt
            if 'last_night_avg' in hrv_df.columns and not hrv_df.empty:
                hrv_df['rolling_avg_7d'] = hrv_df['last_night_avg'].rolling(window=7, min_periods=1).mean()
            else:
                hrv_df['rolling_avg_7d'] = None
            
            # Konverter til liste av dictionaries, gjør om indeksen til en kolonne
            hrv_data = hrv_df.reset_index().replace({np.nan: None}).to_dict(orient='records')
            
            return {
                "hrv_data": hrv_data,
                "total_records": len(hrv_data)
            }
            
        except Exception as e:
            logger.error(f"Feil ved henting av HRV-data: {e}", exc_info=True)
            return {"hrv_data": [], "error": str(e)}

    def get_activity_details_for_running_economy(self, activity_id: int) -> Optional[pd.DataFrame]:
        """Henter detaljerte data for en spesifikk aktivitet for å beregne løpsøkonomi."""
        details_df = self.storage.activity_details
        activity_details = details_df[details_df['activity_id'] == activity_id]

        if activity_details.empty:
            return None

        # Eksempel på beregning (forenklet)
        # Løpsøkonomi = O2-forbruk (ml/kg/min) / hastighet (m/min)
        # Her bruker vi puls/hastighet som en proxy
        
        # Filtrer for å unngå deling på null
        activity_details = activity_details[activity_details['speed'] > 0]
        if activity_details.empty:
            return None

        activity_details['heart_rate_per_speed'] = activity_details['heart_rate'] / activity_details['speed']
        
        avg_economy = activity_details['heart_rate_per_speed'].mean()
        
        return activity_details[['timestamp', 'heart_rate_per_speed']]

    def calculate_body_battery_start(
        self,
        activity_id: int,
        db: Session,
        *,
        persist: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Beregner Body Battery-nivå ved start av aktivitet.
        Nå basert på faktiske FIT-data verdier som training_stress_score, 
        total_training_effect og total_anaerobic_training_effect.
        """
        try:
            from ..database.models.activity import Activity
            from ..database.models.sleep import Sleep, HRV
            from datetime import datetime, timedelta
            
            # Hent aktivitet fra database
            activity = db.query(Activity).filter(Activity.activity_id == str(activity_id)).first()
            if not activity:
                logger.warning(f"Aktivitet {activity_id} ikke funnet i database")
                return None
            
            # Hvis allerede beregnet, returner cached verdi
            if activity.body_battery_start is not None:
                if activity.body_battery_start < 0:
                    return {
                        "activity_id": activity_id,
                        "body_battery_start": None,
                        "availability": "unavailable",
                        "source": "activity_db",
                        "calculation_method": "cached_unavailable",
                        "reason": "Markert som utilgjengelig i activities (f.eks. -1 fra precompute).",
                    }
                return {
                    "activity_id": activity_id,
                    "body_battery_start": round(activity.body_battery_start, 1),
                    "availability": "estimated",
                    "source": "activity_db",
                    "calculation_method": "cached",
                    "reason": "Lagret estimat; Garmin leverer ikke Body Battery ved aktivitetsstart direkte.",
                }
            
            # Hent dato for aktiviteten
            activity_date = activity.start_time.date()
            previous_night = activity_date - timedelta(days=1)
            
            # Base Body Battery basert på tid på dagen (mer realistisk)
            hour = activity.start_time.hour
            if 5 <= hour <= 7:  # Tidlig morgen
                base_body_battery = 50.0
            elif 8 <= hour <= 11:  # Formiddag
                base_body_battery = 60.0
            elif 12 <= hour <= 15:  # Ettermiddag
                base_body_battery = 55.0
            elif 16 <= hour <= 19:  # Kveld
                base_body_battery = 50.0
            else:  # Natt/sent kveld
                base_body_battery = 40.0
            
            # 1. Søvnfaktor basert på faktisk søvndata (0-25 poeng)
            sleep_factor = 0.0
            sleep_data = db.query(Sleep).filter(Sleep.sleep_date == previous_night).first()
            if sleep_data:
                if sleep_data.sleep_score:
                    # Bruk faktisk søvnscore (0-100) og konverter til 0-25 poeng
                    sleep_factor = (sleep_data.sleep_score / 100) * 25
                elif sleep_data.total_sleep_time:
                    # Beregn basert på søvnvarighet
                    sleep_hours = sleep_data.total_sleep_time / 3600
                    if sleep_hours >= 8:
                        sleep_factor = 25
                    elif sleep_hours >= 7:
                        sleep_factor = 20
                    elif sleep_hours >= 6:
                        sleep_factor = 15
                    elif sleep_hours >= 5:
                        sleep_factor = 10
                    else:
                        sleep_factor = 5
                
                # Juster basert på søvneffektivitet hvis tilgjengelig
                if sleep_data.sleep_efficiency and sleep_data.sleep_efficiency > 0:
                    efficiency_multiplier = min(sleep_data.sleep_efficiency / 85, 1.2)  # 85% = optimal
                    sleep_factor *= efficiency_multiplier
            else:
                # Fallback - estimat basert på tid og ukedag
                weekday = activity.start_time.weekday()
                if weekday in [5, 6]:  # Helg
                    sleep_factor = 18 if hour <= 8 else 20
                else:  # Ukedag
                    sleep_factor = 12 if hour <= 6 else 15
            
            # 2. HRV-faktor basert på faktisk HRV-data (-15 til +15 poeng)
            hrv_factor = 0.0
            try:
                morning_hrv = db.query(HRV).filter(
                    HRV.measurement_date == activity_date,
                    HRV.measurement_type.in_(['morning', 'during_sleep'])
                ).order_by(HRV.measurement_time.desc()).first()
                
                if morning_hrv and morning_hrv.rmssd:
                    # Sammenlign med baseline (gjennomsnitt siste 7 dager)
                    week_ago = activity_date - timedelta(days=7)
                    recent_hrvs = db.query(HRV).filter(
                        HRV.measurement_date >= week_ago,
                        HRV.measurement_date < activity_date,
                        HRV.rmssd.isnot(None)
                    ).all()
                    
                    if recent_hrvs:
                        avg_hrv = sum(h.rmssd for h in recent_hrvs) / len(recent_hrvs)
                        hrv_ratio = morning_hrv.rmssd / avg_hrv
                        
                        if hrv_ratio > 1.15:  # 15% over baseline - utmerket
                            hrv_factor = 15
                        elif hrv_ratio > 1.08:  # 8% over baseline - godt
                            hrv_factor = 10
                        elif hrv_ratio > 1.03:  # 3% over baseline - litt over
                            hrv_factor = 5
                        elif hrv_ratio < 0.85:  # 15% under baseline - dårlig
                            hrv_factor = -15
                        elif hrv_ratio < 0.92:  # 8% under baseline - ikke optimalt
                            hrv_factor = -10
                        elif hrv_ratio < 0.97:  # 3% under baseline - litt under
                            hrv_factor = -5
                        else:
                            hrv_factor = 0
                    else:
                        # Bruk stress score som backup
                        if morning_hrv.stress_score:
                            if morning_hrv.stress_score < 20:
                                hrv_factor = 12
                            elif morning_hrv.stress_score < 40:
                                hrv_factor = 5
                            elif morning_hrv.stress_score > 80:
                                hrv_factor = -12
                            elif morning_hrv.stress_score > 60:
                                hrv_factor = -8
            except Exception as e:
                logger.warning(f"Kunne ikke beregne HRV-faktor for aktivitet {activity_id}: {e}")
            
            # 3. Forrige treningsbelastning basert på faktiske FIT-data (-20 til +5 poeng)
            training_load_factor = 0.0
            try:
                # Finn forrige aktivitet
                previous_activity = db.query(Activity).filter(
                    Activity.start_time < activity.start_time
                ).order_by(Activity.start_time.desc()).first()
                
                if previous_activity:
                    hours_since = (activity.start_time - previous_activity.start_time).total_seconds() / 3600
                    
                    # Bruk faktisk TSS hvis tilgjengelig
                    if previous_activity.training_stress_score:
                        tss = previous_activity.training_stress_score
                        
                        # Beregn recovery basert på TSS og tid
                        if tss >= 300:  # Meget høy belastning
                            required_recovery = 72  # 3 dager
                        elif tss >= 200:  # Høy belastning
                            required_recovery = 48  # 2 dager
                        elif tss >= 150:  # Moderat belastning
                            required_recovery = 24  # 1 dag
                        elif tss >= 100:  # Lett belastning
                            required_recovery = 12  # 12 timer
                        else:  # Minimal belastning
                            required_recovery = 6   # 6 timer
                        
                        recovery_ratio = hours_since / required_recovery
                        
                        if recovery_ratio >= 1.5:  # Overrecovered
                            training_load_factor = 5
                        elif recovery_ratio >= 1.0:  # Fullt restituert
                            training_load_factor = 0
                        elif recovery_ratio >= 0.75:  # Mest restituert
                            training_load_factor = -5
                        elif recovery_ratio >= 0.5:  # Delvis restituert
                            training_load_factor = -10
                        else:  # Underrecovered
                            training_load_factor = -20
                    
                    # Bruk Training Effect verdier hvis TSS ikke er tilgjengelig
                    elif previous_activity.total_training_effect or previous_activity.total_anaerobic_training_effect:
                        aerobic_effect = previous_activity.total_training_effect or 0
                        anaerobic_effect = previous_activity.total_anaerobic_training_effect or 0
                        combined_effect = aerobic_effect + anaerobic_effect
                        
                        # Høyere Training Effect = mer recovery tid nødvendig
                        if combined_effect >= 8.0:  # Meget høy effekt
                            required_recovery = 48
                        elif combined_effect >= 6.0:  # Høy effekt
                            required_recovery = 24
                        elif combined_effect >= 4.0:  # Moderat effekt
                            required_recovery = 12
                        elif combined_effect >= 2.0:  # Lett effekt
                            required_recovery = 8
                        else:  # Minimal effekt
                            required_recovery = 4
                        
                        recovery_ratio = hours_since / required_recovery
                        
                        if recovery_ratio >= 1.0:
                            training_load_factor = 0
                        elif recovery_ratio >= 0.75:
                            training_load_factor = -3
                        elif recovery_ratio >= 0.5:
                            training_load_factor = -8
                        else:
                            training_load_factor = -15
                    else:
                        # Fallback til enkelt tid-basert estimat
                        if hours_since >= 48:
                            training_load_factor = 3
                        elif hours_since >= 24:
                            training_load_factor = 0
                        elif hours_since >= 12:
                            training_load_factor = -5
                        else:
                            training_load_factor = -10
                else:
                    # Ingen tidligere aktivitet - fullt restituert
                    training_load_factor = 5
            except Exception as e:
                logger.warning(f"Kunne ikke beregne treningsbelastnings-faktor: {e}")
            
            # 4. Stressfaktor basert på søvndata (-8 til 0 poeng)
            stress_factor = 0.0
            if sleep_data and sleep_data.stress_score:
                if sleep_data.stress_score > 85:
                    stress_factor = -8
                elif sleep_data.stress_score > 70:
                    stress_factor = -5
                elif sleep_data.stress_score > 50:
                    stress_factor = -2
            
            # 5. Aktivitetstid-faktor (justerer basert på når på dagen)
            time_factor = 0.0
            if 6 <= hour <= 9:  # Morgentrening - ofte optimalt
                time_factor = 5
            elif 10 <= hour <= 14:  # Midt på dagen
                time_factor = 2
            elif 15 <= hour <= 18:  # Ettermiddagstrening
                time_factor = 0
            elif hour >= 19:  # Kveldstrening - kan være mer krevende
                time_factor = -3
            else:  # Tidlig morgen/sent kveld
                time_factor = -2
            
            # Legg til litt naturlig variasjon basert på aktivitets-ID
            variation_factor = ((activity_id % 47) / 47 * 6) - 3  # -3 til +3 basert på ID
            
            # Beregn total Body Battery
            body_battery = (base_body_battery + sleep_factor + hrv_factor + 
                          training_load_factor + stress_factor + time_factor + variation_factor)
            
            # Begrens til 5-95 range (realistisk Body Battery range før trening)
            body_battery = max(5, min(95, body_battery))
            
            activity.body_battery_start = body_battery
            self._maybe_commit(db, persist=persist)

            # Legg til informasjon om FIT-data som ble brukt
            fit_data_used = {
                "tss": activity.training_stress_score if hasattr(activity, 'training_stress_score') else None,
                "aerobic_effect": activity.total_training_effect if hasattr(activity, 'total_training_effect') else None,
                "anaerobic_effect": activity.total_anaerobic_training_effect if hasattr(activity, 'total_anaerobic_training_effect') else None
            }
            
            logger.debug(
                "Beregnet Body Battery for aktivitet %s: %.1f (base: %.1f, søvn: +%.1f, HRV: %+.1f, "
                "belastning: %+.1f, stress: %+.1f, tid: %+.1f, var: %+.1f) FIT-data: %s",
                activity_id,
                body_battery,
                base_body_battery,
                sleep_factor,
                hrv_factor,
                training_load_factor,
                stress_factor,
                time_factor,
                variation_factor,
                fit_data_used,
            )
            
            return {
                "activity_id": activity_id,
                "body_battery_start": round(body_battery, 1),
                "availability": "estimated",
                "source": "analysis_service_heuristic",
                "calculation_method": "fit_data_enhanced",
                "reason": "Heuristisk estimat fra søvn, HRV, belastning og tid på dagen.",
                "factors": {
                    "base": round(base_body_battery, 1),
                    "sleep": round(sleep_factor, 1),
                    "hrv": round(hrv_factor, 1),
                    "training_load": round(training_load_factor, 1),
                    "stress": round(stress_factor, 1),
                    "time": round(time_factor, 1),
                    "variation": round(variation_factor, 1)
                },
                "fit_data_used": fit_data_used
            }
            
        except Exception as e:
            logger.error(f"Feil ved beregning av Body Battery for aktivitet {activity_id}: {e}")
            return None
