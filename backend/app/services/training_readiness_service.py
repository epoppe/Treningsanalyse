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

class TrainingReadinessService:
    """Service for å beregne training readiness score."""
    
    def __init__(self):
        self.db = SessionLocal()
        self.tss_service = TrainingStressService(self.db)
    
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
            
            # 4. Hent form-score (Training Stress Balance)
            form_score_value = self._get_form_score(target_date)
            
            # 5. Beregn komponenter
            sleep_score = self._calculate_sleep_score(sleep_data)
            hrv_score = self._calculate_hrv_score(hrv_data)
            form_score = self._calculate_form_score(form_score_value)
            
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
                "details": {
                    "sleep_data": sleep_data,
                    "hrv_data": hrv_data,
                    "activity_data": activity_data,
                    "form_value": form_score_value
                }
            }
            
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
    
    def _calculate_sleep_score(self, sleep_data: List[Dict[str, Any]]) -> float:
        """
        Beregn søvnscore (0-100) basert på siste 3 netter.
        
        Normalisering: Garmin sleep score svinger mellom 65-100
        - 65 eller lavere → 0
        - 100 → 100
        - Lineær skalering mellom
        """
        print("=== NY SLEEP BEREGNING KJØRER ===")
        if not sleep_data:
            return 50.0  # Middels score hvis ingen data
        
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
            avg_score = sum(scores) / len(scores)
            logger.info(f"Sleep score: Garmin scores={[sleep.get('overall_score') or sleep.get('sleep_score') for sleep in recent_sleep]}, Normalized={avg_score:.1f}")
            return round(avg_score, 1)
        
        return 50.0
    
    def _calculate_hrv_score(self, hrv_data: List[Dict[str, Any]]) -> float:
        """
        Beregn HRV-score (0-100).
        
        Normalisering: HRV (RMSSD) svinger mellom 35-43 ms
        - 35 eller lavere → 0
        - 43 eller høyere → 100
        - Lineær skalering mellom
        """
        if not hrv_data:
            return 50.0  # Middels score hvis ingen data
        
        # Fokuser på morgendata
        morning_hrv = [h for h in hrv_data if h.get('measurement_type') in ['morning', 'during_sleep']]
        
        if not morning_hrv:
            return 50.0
        
        # Beregn gjennomsnittlig RMSSD
        rmssd_values = [h['rmssd'] for h in morning_hrv if h.get('rmssd')]
        
        if not rmssd_values:
            return 50.0
        
        avg_rmssd = sum(rmssd_values) / len(rmssd_values)
        
        # Normaliser fra 35-43 til 0-100
        # Formel: (avg_rmssd - 35) / (43 - 35) * 100
        normalized = max(0, min(100, (avg_rmssd - 35) / 8 * 100))
        
        logger.info(f"HRV score: Raw RMSSD={avg_rmssd:.1f} ms, Normalized={normalized:.1f}")
        return round(normalized, 1)
    
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
    
    def _get_form_score(self, target_date: date) -> float:
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
                return 0.0
            
            # Bruk sammendrag fra siste dag (som tilsvarer end_date = target_date)
            summary = metrics.get('summary', {})
            if summary and summary.get('current_form') is not None:
                current_ctl = summary.get('current_ctl', 0)
                current_atl = summary.get('current_atl', 0)
                current_form = summary.get('current_form', 0)
                
                logger.debug(f"Form-score for {target_date}: {current_form} (CTL: {current_ctl}, ATL: {current_atl})")
                return current_form
            
            # Fallback: Prøv å finne i daily_data
            daily_data = metrics.get('daily_data', [])
            target_date_str = target_date.isoformat()
            
            for day in reversed(daily_data):  # Start fra slutten (nyeste først)
                if day['date'] == target_date_str:
                    form_value = day.get('form', 0)
                    logger.debug(f"Form-score for {target_date}: {form_value} (CTL: {day.get('ctl', 0)}, ATL: {day.get('atl', 0)})")
                    return form_value
            
            # Hvis ingen data for denne dagen, returner 0 (balanced)
            logger.warning(f"Ingen form-data funnet for {target_date}, bruker 0 (balanced)")
            return 0.0
            
        except Exception as e:
            logger.error(f"Feil ved henting av form-score: {e}", exc_info=True)
            return 0.0
    
    def _calculate_form_score(self, form_value: float) -> float:
        """
        Konverter Training Stress Balance (Form/TSB) til readiness score (0-100).
        
        Normalisering: Form svinger mellom -40 til +40
        - -40 eller lavere → 0 (høy fatigue)
        - +40 eller høyere → 100 (meget frisk)
        - 0 (balanced) → 50
        - Lineær skalering mellom
        
        Formel: (form_value + 40) / 80 * 100
        """
        # Normaliser fra -40 til +40 til 0-100
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