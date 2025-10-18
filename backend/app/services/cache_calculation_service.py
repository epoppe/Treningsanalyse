"""
Service for å beregne og cache alle beregnede verdier i databasen.
Dette gjør at vi ikke trenger å beregne verdier on-the-fly hver gang.
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from ..database.models.activity import Activity
from ..storage import DataStorage
from .power_service import PowerService
from .training_stress_service import TrainingStressService
from .analysis_service import AnalysisService

logger = logging.getLogger(__name__)

class CacheCalculationService:
    """
    Service for å beregne og lagre alle beregnede verdier i databasen.
    """
    
    def __init__(self, db: Session, storage: DataStorage):
        self.db = db
        self.storage = storage
        self.power_service = PowerService(storage)
        self.tss_service = TrainingStressService(db)
        self.analysis_service = AnalysisService(storage)
    
    def calculate_and_cache_activity(self, activity_id: str, force_recalculate: bool = False) -> dict:
        """
        Beregn og lagre alle beregnede verdier for en enkelt aktivitet.
        
        Args:
            activity_id: Aktivitetens ID
            force_recalculate: Hvis True, beregn på nytt selv om verdier finnes
            
        Returns:
            Dictionary med status for hver beregning
        """
        activity = self.db.query(Activity).filter(Activity.activity_id == activity_id).first()
        if not activity:
            logger.warning(f"Aktivitet {activity_id} ikke funnet")
            return {"error": "Activity not found"}
        
        results = {
            "activity_id": activity_id,
            "calculations": {}
        }
        
        # 1. TSS (Training Stress Score) - bruker EPOC hvis tilgjengelig
        if force_recalculate or activity.training_stress_score is None:
            try:
                tss = self.tss_service.calculate_tss_for_activity(activity)
                activity.training_stress_score = tss
                results["calculations"]["tss"] = {"value": tss, "status": "calculated"}
                logger.debug(f"Beregnet TSS for {activity_id}: {tss}")
            except Exception as e:
                logger.error(f"Feil ved beregning av TSS for {activity_id}: {e}")
                results["calculations"]["tss"] = {"status": "error", "message": str(e)}
        else:
            results["calculations"]["tss"] = {"value": activity.training_stress_score, "status": "cached"}
        
        # 2. Power (kun for løpeaktiviteter)
        if activity.activity_type and activity.activity_type.type_key == 'running':
            if force_recalculate or activity.average_power is None:
                try:
                    power_data = self.power_service.calculate_activity_power(int(activity_id), self.db)
                    if power_data:
                        # Power lagres allerede i calculate_activity_power
                        results["calculations"]["power"] = {
                            "avg": power_data.get("average_power_watts"),
                            "max": power_data.get("max_power_watts"),
                            "status": "calculated"
                        }
                        logger.debug(f"Beregnet power for {activity_id}: {power_data.get('average_power_watts')}W")
                except Exception as e:
                    logger.error(f"Feil ved beregning av power for {activity_id}: {e}")
                    results["calculations"]["power"] = {"status": "error", "message": str(e)}
            else:
                results["calculations"]["power"] = {
                    "avg": activity.average_power,
                    "max": activity.max_power,
                    "status": "cached"
                }
        
        # 3. Running Economy (hastighet/puls-forhold)
        if activity.activity_type and 'running' in activity.activity_type.type_key:
            if force_recalculate or activity.running_economy is None:
                try:
                    if activity.average_speed and activity.average_heart_rate and activity.average_speed > 0 and activity.average_heart_rate > 0:
                        # Running economy = (speed in km/h / HR) * 100
                        speed_kmh = activity.average_speed * 3.6
                        running_economy = (speed_kmh / activity.average_heart_rate) * 100
                        activity.running_economy = round(running_economy, 2)
                        results["calculations"]["running_economy"] = {
                            "value": running_economy,
                            "status": "calculated"
                        }
                        logger.debug(f"Beregnet løpsøkonomi for {activity_id}: {running_economy}")
                except Exception as e:
                    logger.error(f"Feil ved beregning av løpsøkonomi for {activity_id}: {e}")
                    results["calculations"]["running_economy"] = {"status": "error", "message": str(e)}
            else:
                results["calculations"]["running_economy"] = {
                    "value": activity.running_economy,
                    "status": "cached"
                }
        
        # 4. Negative Split (fra FIT-data hvis tilgjengelig)
        if force_recalculate or activity.negative_split_percent is None:
            try:
                negative_split = self.analysis_service.calculate_negative_split(int(activity_id), self.db)
                if negative_split and 'negative_split_percent' in negative_split:
                    activity.negative_split_percent = negative_split['negative_split_percent']
                    results["calculations"]["negative_split"] = {
                        "value": negative_split['negative_split_percent'],
                        "status": "calculated"
                    }
                    logger.debug(f"Beregnet negative split for {activity_id}: {negative_split['negative_split_percent']}%")
            except Exception as e:
                logger.debug(f"Kunne ikke beregne negative split for {activity_id}: {e}")
                results["calculations"]["negative_split"] = {"status": "skipped", "message": "No FIT data"}
        else:
            results["calculations"]["negative_split"] = {
                "value": activity.negative_split_percent,
                "status": "cached"
            }
        
        # 5. Decoupling (fra FIT-data hvis tilgjengelig)
        if force_recalculate or activity.decoupling_percent is None:
            try:
                decoupling = self.analysis_service.calculate_decoupling(int(activity_id), self.db)
                if decoupling and 'decoupling_percent' in decoupling:
                    activity.decoupling_percent = decoupling['decoupling_percent']
                    results["calculations"]["decoupling"] = {
                        "value": decoupling['decoupling_percent'],
                        "status": "calculated"
                    }
                    logger.debug(f"Beregnet decoupling for {activity_id}: {decoupling['decoupling_percent']}%")
            except Exception as e:
                logger.debug(f"Kunne ikke beregne decoupling for {activity_id}: {e}")
                results["calculations"]["decoupling"] = {"status": "skipped", "message": "No FIT data"}
        else:
            results["calculations"]["decoupling"] = {
                "value": activity.decoupling_percent,
                "status": "cached"
            }
        
        # Commit alle endringer
        try:
            self.db.commit()
            results["status"] = "success"
            logger.info(f"Lagret alle beregnede verdier for aktivitet {activity_id}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Feil ved lagring av beregnede verdier for {activity_id}: {e}")
            results["status"] = "error"
            results["error"] = str(e)
        
        return results
    
    def calculate_and_cache_all_activities(
        self, 
        force_recalculate: bool = False, 
        limit: Optional[int] = None,
        only_missing: bool = True
    ) -> dict:
        """
        Beregn og lagre alle beregnede verdier for alle aktiviteter.
        
        Args:
            force_recalculate: Hvis True, beregn på nytt selv om verdier finnes
            limit: Maksimalt antall aktiviteter å prosessere
            only_missing: Hvis True, beregn kun for aktiviteter som mangler verdier
            
        Returns:
            Dictionary med statistikk over prosesseringen
        """
        logger.info("Starter beregning av alle cache-verdier...")
        
        # Hent aktiviteter
        query = self.db.query(Activity)
        
        if only_missing and not force_recalculate:
            # Kun aktiviteter som mangler minst én beregnet verdi
            query = query.filter(
                (Activity.training_stress_score == None) |
                (Activity.running_economy == None) |
                (Activity.negative_split_percent == None)
            )
        
        if limit:
            query = query.limit(limit)
        
        activities = query.all()
        
        stats = {
            "total_activities": len(activities),
            "processed": 0,
            "success": 0,
            "errors": 0,
            "skipped": 0
        }
        
        for activity in activities:
            try:
                result = self.calculate_and_cache_activity(activity.activity_id, force_recalculate)
                stats["processed"] += 1
                
                if result.get("status") == "success":
                    stats["success"] += 1
                elif result.get("status") == "error":
                    stats["errors"] += 1
                else:
                    stats["skipped"] += 1
                
                # Log progress hver 50. aktivitet
                if stats["processed"] % 50 == 0:
                    logger.info(f"Prosessert {stats['processed']}/{stats['total_activities']} aktiviteter...")
                    
            except Exception as e:
                logger.error(f"Feil ved prosessering av aktivitet {activity.activity_id}: {e}")
                stats["errors"] += 1
        
        logger.info(f"Ferdig! Prosessert {stats['processed']} aktiviteter: "
                   f"{stats['success']} suksess, {stats['errors']} feil, {stats['skipped']} hoppet over")
        
        return stats
