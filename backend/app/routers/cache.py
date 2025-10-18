"""
Router for cache-beregninger.
Gir endepunkter for å beregne og lagre beregnede verdier i databasen.
"""

from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from ..database.session import get_db
from ..dependencies import get_data_storage
from ..storage import DataStorage
from ..services.cache_calculation_service import CacheCalculationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cache",
    tags=["Cache"]
)

@router.post("/calculate-all")
async def calculate_all_cache_values(
    background_tasks: BackgroundTasks,
    force_recalculate: bool = Query(False, description="Beregn på nytt selv om verdier finnes"),
    limit: Optional[int] = Query(None, description="Maksimalt antall aktiviteter å prosessere"),
    only_missing: bool = Query(True, description="Kun beregn for aktiviteter som mangler verdier"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage)
):
    """
    Beregn og lagre alle cache-verdier for aktiviteter i bakgrunnen.
    
    Dette inkluderer:
    - TSS (Training Stress Score)
    - Power (for løpeaktiviteter)
    - Running Economy
    - Negative Split
    - Decoupling
    """
    logger.info("Starter cache-beregning i bakgrunnen...")
    
    def run_calculations():
        # Opprett en ny database-sesjon for bakgrunns-jobben
        from ..database.session import SessionLocal
        db_session = SessionLocal()
        try:
            service = CacheCalculationService(db_session, storage)
            stats = service.calculate_and_cache_all_activities(
                force_recalculate=force_recalculate,
                limit=limit,
                only_missing=only_missing
            )
            logger.info(f"Cache-beregning fullført: {stats}")
        finally:
            db_session.close()
    
    background_tasks.add_task(run_calculations)
    
    return {
        "message": "Cache-beregning startet i bakgrunnen",
        "force_recalculate": force_recalculate,
        "limit": limit,
        "only_missing": only_missing
    }

@router.post("/calculate-activity/{activity_id}")
async def calculate_activity_cache_values(
    activity_id: str,
    force_recalculate: bool = Query(False, description="Beregn på nytt selv om verdier finnes"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage)
):
    """
    Beregn og lagre cache-verdier for en enkelt aktivitet.
    """
    service = CacheCalculationService(db, storage)
    result = service.calculate_and_cache_activity(activity_id, force_recalculate)
    
    return result

@router.get("/stats")
async def get_cache_stats(
    db: Session = Depends(get_db)
):
    """
    Hent statistikk over hvilke aktiviteter som har cache-verdier.
    """
    from sqlalchemy import func
    from ..database.models.activity import Activity
    
    total_activities = db.query(func.count(Activity.activity_id)).scalar()
    
    stats = {
        "total_activities": total_activities,
        "cached_values": {
            "tss": db.query(func.count(Activity.activity_id)).filter(
                Activity.training_stress_score != None
            ).scalar(),
            "power": db.query(func.count(Activity.activity_id)).filter(
                Activity.average_power != None
            ).scalar(),
            "running_economy": db.query(func.count(Activity.activity_id)).filter(
                Activity.running_economy != None
            ).scalar(),
            "negative_split": db.query(func.count(Activity.activity_id)).filter(
                Activity.negative_split_percent != None
            ).scalar(),
            "decoupling": db.query(func.count(Activity.activity_id)).filter(
                Activity.decoupling_percent != None
            ).scalar(),
        }
    }
    
    # Beregn prosent
    for key, count in stats["cached_values"].items():
        percentage = (count / total_activities * 100) if total_activities > 0 else 0
        stats["cached_values"][key] = {
            "count": count,
            "percentage": round(percentage, 1)
        }
    
    return stats
