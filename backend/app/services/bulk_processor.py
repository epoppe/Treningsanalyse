"""
Bulk Processing Service for Treningsanalyse
Handles batch operations for power, TSS, and other calculations
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import update, and_, or_
from datetime import datetime, timedelta

from ..database.models.activity import Activity, ActivityType
from ..storage import DataStorage
from .power_service import PowerService
from .training_stress_service import TrainingStressService
from ..cache.cache_manager import get_cache_manager

logger = logging.getLogger(__name__)

class BulkProcessor:
    """Handles bulk processing of activities for better performance"""
    
    def __init__(self, db: Session, storage: Optional[DataStorage] = None):
        self.db = db
        self.storage = storage or DataStorage()
        self.power_service = PowerService(self.storage)
        self.cache = get_cache_manager()
    
    async def bulk_calculate_power(
        self, 
        activity_ids: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        only_missing: bool = True,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Beregn power for flere aktiviteter i bulk
        
        Args:
            activity_ids: Spesifikke aktivitets-IDer (valgfritt)
            start_date: Start dato for periode (valgfritt)
            end_date: Slutt dato for periode (valgfritt)
            only_missing: Kun beregn for aktiviteter som mangler power
            limit: Maksimalt antall aktiviteter å prosessere
            
        Returns:
            Dict med statistikk over prosessering
        """
        logger.info("🔧 Starter bulk power-beregning...")
        
        # Bygg query
        query = self.db.query(Activity).join(ActivityType).filter(
            ActivityType.type_key == 'running'  # Kun løping
        )
        
        # Filtrer på IDs hvis spesifisert
        if activity_ids:
            query = query.filter(Activity.activity_id.in_(activity_ids))
        
        # Filtrer på dato hvis spesifisert
        if start_date:
            query = query.filter(Activity.start_time >= start_date)
        if end_date:
            query = query.filter(Activity.start_time <= end_date)
        
        # Kun aktiviteter som mangler power
        if only_missing:
            query = query.filter(Activity.average_power.is_(None))
        
        # Limit
        if limit:
            query = query.limit(limit)
        
        activities = query.all()
        total_count = len(activities)
        
        if total_count == 0:
            logger.info("✅ Ingen aktiviteter trenger power-beregning")
            return {
                'total': 0,
                'processed': 0,
                'cached': 0,
                'calculated': 0,
                'failed': 0
            }
        
        logger.info(f"📊 Fant {total_count} aktiviteter som trenger power-beregning")
        
        # Process i batches for bedre ytelse
        batch_size = 50
        processed = 0
        cached = 0
        calculated = 0
        failed = 0
        
        for i in range(0, total_count, batch_size):
            batch = activities[i:i + batch_size]
            logger.info(f"⚙️ Prosesserer batch {i//batch_size + 1}/{(total_count + batch_size - 1)//batch_size}")
            
            # Prosesser batch
            for activity in batch:
                try:
                    # Sjekk cache først
                    cached_power = self.cache.get_power(activity.activity_id)
                    if cached_power:
                        activity.average_power = cached_power['average_power_watts']
                        cached += 1
                    else:
                        # Beregn power
                        result = self.power_service.calculate_activity_power(
                            int(activity.activity_id), 
                            self.db
                        )
                        if result:
                            activity.average_power = result['average_power_watts']
                            # Cache resultatet
                            self.cache.set_power(activity.activity_id, result)
                            calculated += 1
                        else:
                            failed += 1
                    
                    processed += 1
                    
                except Exception as e:
                    logger.warning(f"❌ Feil ved power-beregning for {activity.activity_id}: {e}")
                    failed += 1
            
            # Commit batch
            try:
                self.db.commit()
                logger.info(f"✅ Batch committed: {processed}/{total_count}")
            except Exception as e:
                logger.error(f"❌ Feil ved commit av batch: {e}")
                self.db.rollback()
        
        result = {
            'total': total_count,
            'processed': processed,
            'cached': cached,
            'calculated': calculated,
            'failed': failed
        }
        
        logger.info(f"✅ Bulk power-beregning fullført: {result}")
        return result
    
    async def bulk_calculate_tss(
        self,
        activity_ids: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        only_missing: bool = True,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Beregn TSS for flere aktiviteter i bulk
        
        Args:
            activity_ids: Spesifikke aktivitets-IDer (valgfritt)
            start_date: Start dato for periode (valgfritt)
            end_date: Slutt dato for periode (valgfritt)
            only_missing: Kun beregn for aktiviteter som mangler TSS
            limit: Maksimalt antall aktiviteter å prosessere
            
        Returns:
            Dict med statistikk over prosessering
        """
        logger.info("🔧 Starter bulk TSS-beregning...")
        
        # Bygg query
        query = self.db.query(Activity)
        
        # Filtrer på IDs hvis spesifisert
        if activity_ids:
            query = query.filter(Activity.activity_id.in_(activity_ids))
        
        # Filtrer på dato hvis spesifisert
        if start_date:
            query = query.filter(Activity.start_time >= start_date)
        if end_date:
            query = query.filter(Activity.start_time <= end_date)
        
        # Kun aktiviteter som mangler TSS
        if only_missing:
            query = query.filter(Activity.training_stress_score.is_(None))
        
        # Limit
        if limit:
            query = query.limit(limit)
        
        activities = query.all()
        total_count = len(activities)
        
        if total_count == 0:
            logger.info("✅ Ingen aktiviteter trenger TSS-beregning")
            return {
                'total': 0,
                'processed': 0,
                'cached': 0,
                'calculated': 0,
                'failed': 0
            }
        
        logger.info(f"📊 Fant {total_count} aktiviteter som trenger TSS-beregning")
        
        # Opprett TrainingStressService
        tss_service = TrainingStressService(self.db)
        
        # Process i batches
        batch_size = 100
        processed = 0
        cached = 0
        calculated = 0
        failed = 0
        
        for i in range(0, total_count, batch_size):
            batch = activities[i:i + batch_size]
            logger.info(f"⚙️ Prosesserer batch {i//batch_size + 1}/{(total_count + batch_size - 1)//batch_size}")
            
            for activity in batch:
                try:
                    # Sjekk cache først
                    cached_tss = self.cache.get_tss(activity.activity_id)
                    if cached_tss:
                        activity.training_stress_score = cached_tss
                        cached += 1
                    else:
                        # Beregn TSS
                        tss = tss_service.calculate_tss(activity)
                        if tss:
                            activity.training_stress_score = tss
                            # Cache resultatet
                            self.cache.set_tss(activity.activity_id, tss)
                            calculated += 1
                        else:
                            failed += 1
                    
                    processed += 1
                    
                except Exception as e:
                    logger.warning(f"❌ Feil ved TSS-beregning for {activity.activity_id}: {e}")
                    failed += 1
            
            # Commit batch
            try:
                self.db.commit()
                logger.info(f"✅ Batch committed: {processed}/{total_count}")
            except Exception as e:
                logger.error(f"❌ Feil ved commit av batch: {e}")
                self.db.rollback()
        
        result = {
            'total': total_count,
            'processed': processed,
            'cached': cached,
            'calculated': calculated,
            'failed': failed
        }
        
        logger.info(f"✅ Bulk TSS-beregning fullført: {result}")
        return result
    
    async def bulk_update_from_cache(self) -> Dict[str, Any]:
        """
        Oppdater database med cached verdier
        Nyttig for å persistere cache-data til database
        
        Returns:
            Dict med statistikk
        """
        logger.info("🔄 Oppdaterer database fra cache...")
        
        # Dette ville kreve å hente alle keys fra Redis
        # For nå, returnerer vi bare en placeholder
        # I produksjon, implementer med Redis SCAN
        
        return {
            'status': 'not_implemented',
            'message': 'Implementer med Redis SCAN for produksjon'
        }
    
    def get_activities_needing_calculation(
        self,
        calculation_type: str,
        limit: int = 100
    ) -> List[Activity]:
        """
        Finn aktiviteter som mangler beregninger
        
        Args:
            calculation_type: 'power', 'tss', 'negative_split', etc.
            limit: Maksimalt antall å returnere
            
        Returns:
            Liste med aktiviteter
        """
        query = self.db.query(Activity)
        
        if calculation_type == 'power':
            query = query.join(ActivityType).filter(
                and_(
                    ActivityType.type_key == 'running',
                    Activity.average_power.is_(None)
                )
            )
        elif calculation_type == 'tss':
            query = query.filter(Activity.training_stress_score.is_(None))
        elif calculation_type == 'negative_split':
            query = query.filter(Activity.negative_split_percent.is_(None))
        elif calculation_type == 'decoupling':
            query = query.filter(Activity.decoupling_percent.is_(None))
        
        return query.limit(limit).all()
















