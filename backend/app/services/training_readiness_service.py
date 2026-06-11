"""
Training Readiness Service basert på garmy-biblioteket.
"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.database.models.activity import Activity
from app.database.models.sleep import Sleep, HRV
from app.database.session import SessionLocal
from app.services.training_stress_service import TrainingStressService

logger = logging.getLogger(__name__)

_READINESS_FALLBACK_SLEEP = frozenset({"fallback_no_data", "fallback_no_scores"})
_READINESS_FALLBACK_HRV = frozenset(
    {"fallback_no_data", "fallback_no_morning_data", "fallback_no_rmssd"}
)
_READINESS_FALLBACK_FORM = frozenset({"fallback_no_metrics", "fallback_error"})


def is_robust_training_readiness(readiness_data: Dict[str, Any]) -> bool:
    """
    True når readiness bygger på reell treningsbelastning (form/TSB) og minst én
    helsekomponent (søvn eller HRV) — ikke ren fallback uten underliggende data.
    """
    if not isinstance(readiness_data, dict) or readiness_data.get("error"):
        return False

    details = readiness_data.get("details") or {}
    sleep_method = (details.get("sleep_baseline") or {}).get("method")
    hrv_method = (details.get("hrv_baseline") or {}).get("method")
    form_method = (details.get("form_baseline") or {}).get("method")

    form_ok = form_method not in _READINESS_FALLBACK_FORM
    health_ok = (
        sleep_method not in _READINESS_FALLBACK_SLEEP
        or hrv_method not in _READINESS_FALLBACK_HRV
    )
    return form_ok and health_ok


class TrainingReadinessService:
    """Service for å beregne training readiness score."""
    
    def __init__(self, db: Optional[Session] = None):
        self.db = db if db is not None else SessionLocal()
        self.tss_service = TrainingStressService(self.db)

    def _percentile(self, values: List[float], percentile: float) -> Optional[float]:
        cleaned = sorted(float(v) for v in values if v is not None)
        if not cleaned:
            return None
        if len(cleaned) == 1:
            return cleaned[0]
        rank = (len(cleaned) - 1) * percentile
        lower = int(rank)
        upper = min(lower + 1, len(cleaned) - 1)
        weight = rank - lower
        return cleaned[lower] * (1 - weight) + cleaned[upper] * weight

    def _score_against_baseline(
        self,
        value: Optional[float],
        low: Optional[float],
        mid: Optional[float],
        high: Optional[float],
    ) -> Optional[float]:
        if value is None or low is None or mid is None or high is None:
            return None
        if not (low < mid < high):
            return None
        if value <= mid:
            span = mid - low
            if span <= 0:
                return None
            normalized = ((value - low) / span) * 50.0
        else:
            span = high - mid
            if span <= 0:
                return None
            normalized = 50.0 + ((value - mid) / span) * 50.0
        return max(0.0, min(100.0, normalized))

    def _get_sleep_baseline(self, target_date: date) -> Optional[Dict[str, float]]:
        baseline_end = target_date - timedelta(days=4)
        baseline_start = baseline_end - timedelta(days=41)
        sleep_rows = self.db.query(Sleep).filter(
            and_(
                Sleep.sleep_date >= baseline_start,
                Sleep.sleep_date <= baseline_end,
            )
        ).all()
        values = [
            float(score)
            for row in sleep_rows
            for score in [(row.overall_score or row.sleep_score)]
            if score is not None
        ]
        if len(values) < 7:
            return None
        p10 = self._percentile(values, 0.10)
        p50 = self._percentile(values, 0.50)
        p90 = self._percentile(values, 0.90)
        if p10 is None or p50 is None or p90 is None:
            return None
        return {
            "method": "personal_sleep_percentiles",
            "low": round(p10, 1),
            "mid": round(p50, 1),
            "high": round(p90, 1),
            "sample_count": float(len(values)),
        }

    def _get_hrv_baseline(self, target_date: date) -> Optional[Dict[str, float]]:
        baseline_row = (
            self.db.query(HRV)
            .filter(
                and_(
                    HRV.measurement_date <= target_date,
                    HRV.baseline_balanced_lower.isnot(None),
                    HRV.baseline_balanced_upper.isnot(None),
                )
            )
            .order_by(HRV.measurement_date.desc())
            .first()
        )
        if baseline_row:
            low = baseline_row.baseline_low_upper or baseline_row.baseline_balanced_lower
            high = baseline_row.baseline_balanced_upper
            mid = (baseline_row.baseline_balanced_lower + baseline_row.baseline_balanced_upper) / 2.0
            if low is not None and mid is not None and high is not None and low < mid < high:
                return {
                    "method": "garmin_hrv_baseline",
                    "low": round(float(low), 1),
                    "mid": round(float(mid), 1),
                    "high": round(float(high), 1),
                    "sample_count": 1.0,
                }

        baseline_end = target_date - timedelta(days=4)
        baseline_start = baseline_end - timedelta(days=41)
        hrv_rows = self.db.query(HRV).filter(
            and_(
                HRV.measurement_date >= baseline_start,
                HRV.measurement_date <= baseline_end,
                HRV.rmssd.isnot(None),
            )
        ).all()
        values = [
            float(row.rmssd)
            for row in hrv_rows
            if row.rmssd is not None and row.measurement_type in ["morning", "during_sleep", None]
        ]
        if len(values) < 7:
            return None
        p10 = self._percentile(values, 0.10)
        p50 = self._percentile(values, 0.50)
        p90 = self._percentile(values, 0.90)
        if p10 is None or p50 is None or p90 is None:
            return None
        return {
            "method": "personal_hrv_percentiles",
            "low": round(p10, 1),
            "mid": round(p50, 1),
            "high": round(p90, 1),
            "sample_count": float(len(values)),
        }
    
    def calculate_training_readiness(self, target_date: date = None) -> Dict[str, Any]:
        """
        Beregn training readiness score for en gitt dato.
        Beregner alltid på nytt for å sikre oppdaterte verdier.
        """
        if target_date is None:
            target_date = date.today()
        
        try:
            # Hent data for de siste 7 dagene
            end_date = target_date
            start_date = end_date - timedelta(days=7)
            
            # 1. Hent søvndata
            sleep_data = self._get_sleep_data(start_date, end_date)
            
            # 2. Hent HRV-data
            hrv_data = self._get_hrv_data(start_date, end_date)
            
            # 3. Hent aktivitetsdata
            activity_data = self._get_activity_data(start_date, end_date)
            has_trained_on_date = any(
                activity.get("date") == target_date.isoformat()
                for activity in activity_data
            )
            
            # 4. Hent form-score (Training Stress Balance)
            form_score_value, form_baseline = self._get_form_score(target_date)
            
            # 5. Beregn komponenter
            sleep_score, sleep_baseline = self._calculate_sleep_score(sleep_data, target_date)
            hrv_score, hrv_baseline = self._calculate_hrv_score(hrv_data, target_date)
            form_score = self._calculate_form_score(form_score_value, form_baseline)
            
            # 6. Beregn total score
            total_score = self._calculate_total_score(sleep_score, hrv_score, form_score)
            
            # 6. Bestem readiness status
            readiness_status = self._get_readiness_status(total_score)
            
            result = {
                "date": target_date.isoformat(),
                "total_score": total_score,
                "readiness_status": readiness_status,
                "components": {
                    "sleep_score": sleep_score,
                    "hrv_score": hrv_score,
                    "form_score": form_score
                },
                "has_trained_on_date": has_trained_on_date,
                "is_robust": False,
                "details": {
                    "sleep_data": sleep_data,
                    "hrv_data": hrv_data,
                    "activity_data": activity_data,
                    "form_value": form_score_value,
                    "has_trained_on_date": has_trained_on_date,
                    "sleep_baseline": sleep_baseline,
                    "hrv_baseline": hrv_baseline,
                    "form_baseline": form_baseline,
                }
            }
            result["is_robust"] = is_robust_training_readiness(result)
            
            # 7. Logger info
            logger.info(f"Beregnet readiness for {target_date}: {total_score:.1f} (søvn:{sleep_score:.1f}, hrv:{hrv_score:.1f}, form:{form_score:.1f}, raw form:{form_score_value:.1f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Feil ved beregning av training readiness: {e}")
            return {
                "date": target_date.isoformat(),
                "total_score": 0,
                "readiness_status": "unknown",
                "error": str(e)
            }
    
    def _get_sleep_data(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Hent søvndata for perioden."""
        sleep_records = self.db.query(Sleep).filter(
            and_(
                Sleep.sleep_date >= start_date,
                Sleep.sleep_date <= end_date
            )
        ).all()
        
        return [
            {
                "date": sleep.sleep_date.isoformat(),
                "total_sleep_time": sleep.total_sleep_time,
                "sleep_score": sleep.sleep_score,
                "overall_score": sleep.overall_score,  # Legg til overall_score
                "sleep_efficiency": sleep.sleep_efficiency,
                "stress_score": sleep.stress_score,
                "deep_sleep_time": sleep.deep_sleep_time,
                "light_sleep_time": sleep.light_sleep_time,
                "rem_sleep_time": sleep.rem_sleep_time,
                "awake_time": sleep.awake_time
            }
            for sleep in sleep_records
        ]
    
    def _get_hrv_data(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Hent HRV-data for perioden."""
        hrv_records = self.db.query(HRV).filter(
            and_(
                HRV.measurement_date >= start_date,
                HRV.measurement_date <= end_date
            )
        ).all()
        
        return [
            {
                "date": hrv.measurement_date.isoformat(),
                "time": hrv.measurement_time.isoformat() if hrv.measurement_time else None,
                "rmssd": hrv.rmssd,
                "stress_score": hrv.stress_score,
                "measurement_type": hrv.measurement_type
            }
            for hrv in hrv_records
        ]
    
    def _get_activity_data(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Hent aktivitetsdata for perioden."""
        activities = self.db.query(Activity).filter(
            and_(
                func.date(Activity.start_time) >= start_date,
                func.date(Activity.start_time) <= end_date
            )
        ).order_by(Activity.start_time.desc()).all()
        
        return [
            {
                "activity_id": activity.activity_id,
                "date": activity.start_time.date().isoformat(),
                "start_time": activity.start_time.isoformat(),
                "duration": activity.duration,
                "distance": activity.distance,
                "calories": activity.calories,
                "average_heart_rate": activity.average_heart_rate,
                "training_stress_score": activity.training_stress_score,
                "total_training_effect": activity.total_training_effect,
                "total_anaerobic_training_effect": activity.total_anaerobic_training_effect,
                "recovery_time": activity.recovery_time
            }
            for activity in activities
        ]
    
    def _calculate_sleep_score(
        self,
        sleep_data: List[Dict[str, Any]],
        target_date: date,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Beregn søvnscore (0-100) basert på siste 3 netter.
        
        Normalisering: Garmin sleep score svinger mellom 65-100
        - 65 eller lavere → 0
        - 100 → 100
        - Lineær skalering mellom
        """
        if not sleep_data:
            return 50.0, {"method": "fallback_no_data"}  # Middels score hvis ingen data
        
        # Fokuser på de siste 3 nettene (mest relevant for dagens readiness)
        recent_sleep = sorted(sleep_data, key=lambda x: x['date'], reverse=True)[:3]
        
        scores = []
        for sleep in recent_sleep:
            # Bruk overall_score eller sleep_score fra Garmin
            garmin_score = sleep.get('overall_score') or sleep.get('sleep_score')
            if garmin_score:
                # Normaliser fra 65-100 til 0-100
                # Formel: (garmin_score - 65) / (100 - 65) * 100
                normalized = max(0, min(100, (garmin_score - 65) / 35 * 100))
                scores.append(normalized)
        
        if scores:
            recent_avg = sum(scores) / len(scores)
            baseline = self._get_sleep_baseline(target_date)
            if baseline:
                personalized = self._score_against_baseline(
                    recent_avg,
                    baseline["low"],
                    baseline["mid"],
                    baseline["high"],
                )
                if personalized is not None:
                    logger.info(
                        "Sleep score: recent_avg=%.1f, baseline=%s, normalized=%.1f",
                        recent_avg,
                        baseline,
                        personalized,
                    )
                    return round(personalized, 1), baseline

            normalized = max(0, min(100, (recent_avg - 65) / 35 * 100))
            logger.info(f"Sleep score: Garmin scores={[sleep.get('overall_score') or sleep.get('sleep_score') for sleep in recent_sleep]}, Normalized={normalized:.1f}")
            return round(normalized, 1), {"method": "fallback_fixed_range", "low": 65.0, "mid": 82.5, "high": 100.0}
        
        return 50.0, {"method": "fallback_no_scores"}
    
    def _calculate_hrv_score(
        self,
        hrv_data: List[Dict[str, Any]],
        target_date: date,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Beregn HRV-score (0-100).
        
        Normalisering: HRV (RMSSD) svinger mellom 35-43 ms
        - 35 eller lavere → 0
        - 43 eller høyere → 100
        - Lineær skalering mellom
        """
        if not hrv_data:
            return 50.0, {"method": "fallback_no_data"}  # Middels score hvis ingen data
        
        # Fokuser på morgendata
        morning_hrv = [h for h in hrv_data if h.get('measurement_type') in ['morning', 'during_sleep']]
        
        if not morning_hrv:
            return 50.0, {"method": "fallback_no_morning_data"}
        
        # Beregn gjennomsnittlig RMSSD
        rmssd_values = [h['rmssd'] for h in morning_hrv if h.get('rmssd')]
        
        if not rmssd_values:
            return 50.0, {"method": "fallback_no_rmssd"}
        
        avg_rmssd = sum(rmssd_values) / len(rmssd_values)

        baseline = self._get_hrv_baseline(target_date)
        if baseline:
            personalized = self._score_against_baseline(
                avg_rmssd,
                baseline["low"],
                baseline["mid"],
                baseline["high"],
            )
            if personalized is not None:
                logger.info(
                    "HRV score: avg_rmssd=%.1f, baseline=%s, normalized=%.1f",
                    avg_rmssd,
                    baseline,
                    personalized,
                )
                return round(personalized, 1), baseline
        
        normalized = max(0, min(100, (avg_rmssd - 35) / 8 * 100))
        logger.info(f"HRV score: Raw RMSSD={avg_rmssd:.1f} ms, Normalized={normalized:.1f}")
        return round(normalized, 1), {"method": "fallback_fixed_range", "low": 35.0, "mid": 39.0, "high": 43.0}
    
    def _calculate_activity_score(self, activity_data: List[Dict[str, Any]]) -> float:
        """Beregn aktivitetsscore (0-100)."""
        if not activity_data:
            return 50.0  # Middels score hvis ingen aktiviteter
        
        # Sjekk om det er for mye eller for lite aktivitet
        total_duration = sum(a.get('duration', 0) for a in activity_data)
        total_calories = sum(a.get('calories', 0) for a in activity_data)
        
        # Optimal aktivitet: 3-5 timer per uke
        weekly_hours = total_duration / 3600
        
        if 3 <= weekly_hours <= 5:
            return 90.0
        elif 2 <= weekly_hours <= 6:
            return 80.0
        elif 1 <= weekly_hours <= 7:
            return 70.0
        elif weekly_hours > 7:
            return 40.0  # For mye aktivitet
        else:
            return 30.0  # For lite aktivitet
    
    def _calculate_recovery_score(self, activity_data: List[Dict[str, Any]]) -> float:
        """Beregn recovery score (0-100) basert på tid siden siste aktivitet og intensity."""
        if not activity_data:
            return 100.0  # Full recovery hvis ingen aktiviteter
        
        # Sjekk siste aktivitet
        latest_activity = max(activity_data, key=lambda x: x['start_time'])
        
        # Beregn timer siden siste aktivitet
        last_activity_time = datetime.fromisoformat(latest_activity['start_time'])
        hours_since = (datetime.now() - last_activity_time).total_seconds() / 3600
        
        # Hvis recovery_time er tilgjengelig, bruk den
        if latest_activity.get('recovery_time'):
            recovery_hours = latest_activity['recovery_time']
            
            # Score basert på recovery time
            if recovery_hours <= 12:
                return 30.0  # Trenger mer recovery
            elif recovery_hours <= 24:
                return 60.0
            elif recovery_hours <= 48:
                return 80.0
            else:
                return 100.0  # Full recovery
        
        # Fallback: Bruk tid siden siste aktivitet og intensitet
        # Sjekk også training stress og training effect
        intensity_factor = 1.0
        if latest_activity.get('training_stress_score'):
            tss = latest_activity['training_stress_score']
            if tss > 150:
                intensity_factor = 2.0  # Hard økt krever dobbel recovery
            elif tss > 100:
                intensity_factor = 1.5
        elif latest_activity.get('total_training_effect'):
            te = latest_activity['total_training_effect']
            if te >= 4.0:
                intensity_factor = 1.8
            elif te >= 3.0:
                intensity_factor = 1.3
        
        # Beregn nødvendig recovery tid basert på intensitet
        needed_recovery = 24 * intensity_factor
        recovery_ratio = hours_since / needed_recovery
        
        if recovery_ratio >= 1.0:
            return 100.0  # Full recovery
        elif recovery_ratio >= 0.75:
            return 80.0
        elif recovery_ratio >= 0.5:
            return 60.0
        elif recovery_ratio >= 0.25:
            return 40.0
        else:
            return 30.0  # Trenger mer recovery
    
    def _get_form_score(self, target_date: date) -> Tuple[float, Dict[str, Any]]:
        """
        Hent Training Stress Balance (Form) for en gitt dato.
        Form = CTL - ATL (Chronic Training Load - Acute Training Load)
        """
        try:
            # Hent metrics for en lengre periode for å beregne CTL/ATL
            # CTL = 42 dager, ATL = 7 dager
            start_date = target_date - timedelta(days=60)
            end_date = target_date
            
            metrics_response = self.tss_service.calculate_training_load_metrics_simple(start_date, end_date)
            metrics = metrics_response.get('data', {})
            
            if not metrics:
                logger.warning(f"Ingen metrics data returnert for {target_date}")
                return 0.0, {"method": "fallback_no_metrics"}
            
            # Bruk sammendrag fra siste dag (som tilsvarer end_date = target_date)
            summary = metrics.get('summary', {})
            daily_data = metrics.get('daily_data', [])
            history_values = [
                float(day.get('form', 0))
                for day in daily_data[:-1]
                if day.get('form') is not None
            ]
            form_baseline: Dict[str, Any] = {"method": "fallback_fixed_range", "low": -40.0, "mid": 0.0, "high": 40.0}
            if len(history_values) >= 7:
                p10 = self._percentile(history_values, 0.10)
                p50 = self._percentile(history_values, 0.50)
                p90 = self._percentile(history_values, 0.90)
                if p10 is not None and p50 is not None and p90 is not None and p10 < p50 < p90:
                    form_baseline = {
                        "method": "personal_form_percentiles",
                        "low": round(p10, 1),
                        "mid": round(p50, 1),
                        "high": round(p90, 1),
                        "sample_count": len(history_values),
                    }
            if summary and summary.get('current_form') is not None:
                current_ctl = summary.get('current_ctl', 0)
                current_atl = summary.get('current_atl', 0)
                current_form = summary.get('current_form', 0)
                
                logger.debug(f"Form-score for {target_date}: {current_form} (CTL: {current_ctl}, ATL: {current_atl})")
                return current_form, form_baseline
            
            # Fallback: Prøv å finne i daily_data
            target_date_str = target_date.isoformat()
            
            for day in reversed(daily_data):  # Start fra slutten (nyeste først)
                if day['date'] == target_date_str:
                    form_value = day.get('form', 0)
                    logger.debug(f"Form-score for {target_date}: {form_value} (CTL: {day.get('ctl', 0)}, ATL: {day.get('atl', 0)})")
                    return form_value, form_baseline
            
            # Hvis ingen data for denne dagen, returner 0 (balanced)
            logger.warning(f"Ingen form-data funnet for {target_date}, bruker 0 (balanced)")
            return 0.0, form_baseline
            
        except Exception as e:
            logger.error(f"Feil ved henting av form-score: {e}", exc_info=True)
            return 0.0, {"method": "fallback_error", "low": -40.0, "mid": 0.0, "high": 40.0}
    
    def _calculate_form_score(self, form_value: float, baseline: Optional[Dict[str, Any]] = None) -> float:
        """
        Konverter Training Stress Balance (Form/TSB) til readiness score (0-100).
        
        Normalisering: Form svinger mellom -40 til +40
        - -40 eller lavere → 0 (høy fatigue)
        - +40 eller høyere → 100 (meget frisk)
        - 0 (balanced) → 50
        - Lineær skalering mellom
        
        Formel: (form_value + 40) / 80 * 100
        """
        normalized = None
        if baseline:
            normalized = self._score_against_baseline(
                form_value,
                baseline.get("low"),
                baseline.get("mid"),
                baseline.get("high"),
            )
        if normalized is None:
            normalized = max(0, min(100, (form_value + 40) / 80 * 100))
        
        logger.info(f"Form score: Raw TSB={form_value:.1f}, Normalized={normalized:.1f}")
        return round(normalized, 1)
    
    def _calculate_total_score(self, sleep_score: float, hrv_score: float, 
                             form_score: float) -> float:
        """
        Beregn total training readiness score.
        
        Vektet gjennomsnitt:
        - Søvn: 15% (viktig for recovery)
        - HRV: 15% (indikator på recovery)
        - Form (TSB): 70% (treningsmengde vs recovery - mest kritisk)
        """
        total_score = (
            sleep_score * 0.15 +
            hrv_score * 0.15 +
            form_score * 0.70
        )
        
        logger.info(f"Training Readiness: Sleep={sleep_score:.1f} (15%), HRV={hrv_score:.1f} (15%), Form={form_score:.1f} (70%) => Total={total_score:.1f}")
        
        return round(total_score, 1)
        # Endring for å trigge reload
    
    def _get_readiness_status(self, score: float) -> str:
        """Bestem readiness status basert på score."""
        if score >= 80:
            return "optimal"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "moderate"
        elif score >= 20:
            return "poor"
        else:
            return "very_poor"
    
    def get_weekly_readiness(self, end_date: date = None) -> List[Dict[str, Any]]:
        """Hent training readiness for siste 7 dager."""
        if end_date is None:
            end_date = date.today()
        
        readiness_data = []
        
        for i in range(7):
            target_date = end_date - timedelta(days=i)
            readiness = self.calculate_training_readiness(target_date)
            readiness_data.append(readiness)
        
        return readiness_data
    
    def _get_stored_readiness_score(self, target_date: date) -> Optional[Dict[str, Any]]:
        """Hent lagret readiness score fra databasen."""
        try:
            # Sjekk om det finnes en aktivitet på denne datoen med readiness score
            activity = self.db.query(Activity).filter(
                and_(
                    func.date(Activity.start_time) == target_date,
                    Activity.training_readiness_score.isnot(None)
                )
            ).first()
            
            if activity and activity.training_readiness_score is not None:
                return {
                    "date": target_date.isoformat(),
                    "total_score": activity.training_readiness_score,
                    "readiness_status": self._get_readiness_status(activity.training_readiness_score),
                    "components": {
                        "sleep_score": 0,  # Disse må beregnes på nytt hvis nødvendig
                        "hrv_score": 0,
                        "form_score": 0
                    },
                    "details": {
                        "sleep_data": [],
                        "hrv_data": [],
                        "activity_data": [],
                        "form_value": 0
                    },
                    "from_cache": True
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Feil ved henting av lagret readiness score: {e}")
            return None
    
    def _store_readiness_score(self, target_date: date, readiness_data: Dict[str, Any]) -> bool:
        """Lagre readiness score i databasen."""
        try:
            # Finn aktiviteter på denne datoen og oppdater dem med readiness score
            activities = self.db.query(Activity).filter(
                func.date(Activity.start_time) == target_date
            ).all()
            
            if activities:
                # Oppdater alle aktiviteter på denne datoen med readiness score
                for activity in activities:
                    activity.training_readiness_score = readiness_data["total_score"]
                
                self.db.commit()
                logger.info(f"Lagret readiness score {readiness_data['total_score']} for {len(activities)} aktiviteter på {target_date}")
                return True
            else:
                logger.warning(f"Ingen aktiviteter funnet for {target_date}, kan ikke lagre readiness score")
                return False
                
        except Exception as e:
            logger.error(f"Feil ved lagring av readiness score: {e}")
            self.db.rollback()
            return False
    
    def __del__(self):
        """Cleanup database connection."""
        if hasattr(self, 'db'):
            self.db.close() 
