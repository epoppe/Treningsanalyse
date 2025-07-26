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

logger = logging.getLogger(__name__)

class TrainingReadinessService:
    """Service for å beregne training readiness score."""
    
    def __init__(self):
        self.db = SessionLocal()
    
    def calculate_training_readiness(self, target_date: date = None) -> Dict[str, Any]:
        """
        Beregn training readiness score for en gitt dato.
        Sjekker først om score allerede er lagret i databasen.
        """
        if target_date is None:
            target_date = date.today()
        
        # Sjekk om readiness score allerede er lagret for denne datoen
        stored_score = self._get_stored_readiness_score(target_date)
        if stored_score is not None:
            logger.info(f"Bruker lagret readiness score for {target_date}: {stored_score['total_score']}")
            return stored_score
        
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
            
            # 4. Beregn komponenter
            sleep_score = self._calculate_sleep_score(sleep_data)
            hrv_score = self._calculate_hrv_score(hrv_data)
            activity_score = self._calculate_activity_score(activity_data)
            recovery_score = self._calculate_recovery_score(activity_data)
            
            # 5. Beregn total score
            total_score = self._calculate_total_score(sleep_score, hrv_score, activity_score, recovery_score)
            
            # 6. Bestem readiness status
            readiness_status = self._get_readiness_status(total_score)
            
            result = {
                "date": target_date.isoformat(),
                "total_score": total_score,
                "readiness_status": readiness_status,
                "components": {
                    "sleep_score": sleep_score,
                    "hrv_score": hrv_score,
                    "activity_score": activity_score,
                    "recovery_score": recovery_score
                },
                "details": {
                    "sleep_data": sleep_data,
                    "hrv_data": hrv_data,
                    "activity_data": activity_data
                }
            }
            
            # 7. Lagre score i databasen
            self._store_readiness_score(target_date, result)
            
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
        """Beregn søvnscore (0-100)."""
        if not sleep_data:
            return 50.0  # Middels score hvis ingen data
        
        total_score = 0
        count = 0
        
        for sleep in sleep_data:
            score = 0
            
            # Søvnvarighet (0-40 poeng)
            if sleep.get('total_sleep_time'):
                sleep_hours = sleep['total_sleep_time'] / 3600
                if 7 <= sleep_hours <= 9:
                    score += 40
                elif 6 <= sleep_hours <= 10:
                    score += 30
                elif 5 <= sleep_hours <= 11:
                    score += 20
                else:
                    score += 10
            
            # Søvnscore (0-30 poeng)
            if sleep.get('sleep_score'):
                score += (sleep['sleep_score'] / 100) * 30
            
            # Søvneffektivitet (0-20 poeng)
            if sleep.get('sleep_efficiency'):
                efficiency = sleep['sleep_efficiency']
                if efficiency >= 90:
                    score += 20
                elif efficiency >= 85:
                    score += 15
                elif efficiency >= 80:
                    score += 10
                else:
                    score += 5
            
            # Stress score (0-10 poeng)
            if sleep.get('stress_score'):
                stress = sleep['stress_score']
                if stress <= 25:
                    score += 10
                elif stress <= 50:
                    score += 5
                elif stress <= 75:
                    score += 2
            
            total_score += score
            count += 1
        
        return total_score / count if count > 0 else 50.0
    
    def _calculate_hrv_score(self, hrv_data: List[Dict[str, Any]]) -> float:
        """Beregn HRV-score (0-100)."""
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
        
        # Score basert på RMSSD (forenklet)
        if avg_rmssd >= 50:
            return 90.0
        elif avg_rmssd >= 40:
            return 80.0
        elif avg_rmssd >= 30:
            return 70.0
        elif avg_rmssd >= 20:
            return 60.0
        else:
            return 40.0
    
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
        """Beregn recovery score (0-100)."""
        if not activity_data:
            return 100.0  # Full recovery hvis ingen aktiviteter
        
        # Sjekk siste aktivitet og recovery time
        latest_activity = max(activity_data, key=lambda x: x['start_time'])
        
        if not latest_activity.get('recovery_time'):
            return 70.0  # Middels recovery hvis ingen data
        
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
    
    def _calculate_total_score(self, sleep_score: float, hrv_score: float, 
                             activity_score: float, recovery_score: float) -> float:
        """Beregn total training readiness score."""
        # Vekting av komponenter (basert på garmy-tilnærming)
        weights = {
            'sleep': 0.3,
            'hrv': 0.3,
            'activity': 0.2,
            'recovery': 0.2
        }
        
        total_score = (
            sleep_score * weights['sleep'] +
            hrv_score * weights['hrv'] +
            activity_score * weights['activity'] +
            recovery_score * weights['recovery']
        )
        
        return round(total_score, 1)
    
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
                        "activity_score": 0,
                        "recovery_score": 0
                    },
                    "details": {
                        "sleep_data": [],
                        "hrv_data": [],
                        "activity_data": []
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