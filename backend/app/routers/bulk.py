"""
Bulk Operations Router
Endpoints for batch processing of activities
"""
from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import logging

from ..dependencies import get_db, get_data_storage
from ..storage import DataStorage
from ..services.bulk_processor import BulkProcessor

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/bulk/calculate-power")
async def bulk_calculate_power(
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="Start dato (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Slutt dato (YYYY-MM-DD)"),
    only_missing: bool = Query(True, description="Kun aktiviteter som mangler power"),
    limit: Optional[int] = Query(None, description="Maksimalt antall aktiviteter"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage)
):
    """
    Bulk-beregn power for løpeaktiviteter
    Kjører i bakgrunnen for å ikke blokkere API
    """
    logger.info("🚀 Starter bulk power-beregning i bakgrunnen...")
    
    # Parse datoer
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    
    # Start background task
    async def process():
        processor = BulkProcessor(db, storage)
        result = await processor.bulk_calculate_power(
            start_date=start_dt,
            end_date=end_dt,
            only_missing=only_missing,
            limit=limit
        )
        logger.info(f"✅ Bulk power-beregning fullført: {result}")
    
    background_tasks.add_task(process)
    
    return {
        "status": "started",
        "message": "Bulk power-beregning startet i bakgrunnen",
        "parameters": {
            "start_date": start_date,
            "end_date": end_date,
            "only_missing": only_missing,
            "limit": limit
        }
    }

@router.post("/bulk/calculate-tss")
async def bulk_calculate_tss(
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="Start dato (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Slutt dato (YYYY-MM-DD)"),
    only_missing: bool = Query(True, description="Kun aktiviteter som mangler TSS"),
    limit: Optional[int] = Query(None, description="Maksimalt antall aktiviteter"),
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage)
):
    """
    Bulk-beregn TSS for aktiviteter
    Kjører i bakgrunnen for å ikke blokkere API
    """
    logger.info("🚀 Starter bulk TSS-beregning i bakgrunnen...")
    
    # Parse datoer
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None
    
    # Start background task
    async def process():
        processor = BulkProcessor(db, storage)
        result = await processor.bulk_calculate_tss(
            start_date=start_dt,
            end_date=end_dt,
            only_missing=only_missing,
            limit=limit
        )
        logger.info(f"✅ Bulk TSS-beregning fullført: {result}")
    
    background_tasks.add_task(process)
    
    return {
        "status": "started",
        "message": "Bulk TSS-beregning startet i bakgrunnen",
        "parameters": {
            "start_date": start_date,
            "end_date": end_date,
            "only_missing": only_missing,
            "limit": limit
        }
    }

@router.get("/bulk/status")
async def get_bulk_status(
    db: Session = Depends(get_db),
    storage: DataStorage = Depends(get_data_storage)
):
    """
    Hent status for bulk-operasjoner
    Viser hvor mange aktiviteter som mangler beregninger
    """
    processor = BulkProcessor(db, storage)
    
    # Tell aktiviteter som mangler beregninger
    activities_needing_power = len(processor.get_activities_needing_calculation('power', limit=10000))
    activities_needing_tss = len(processor.get_activities_needing_calculation('tss', limit=10000))
    activities_needing_split = len(processor.get_activities_needing_calculation('negative_split', limit=10000))
    activities_needing_decoupling = len(processor.get_activities_needing_calculation('decoupling', limit=10000))
    
    return {
        "activities_needing_calculations": {
            "power": activities_needing_power,
            "tss": activities_needing_tss,
            "negative_split": activities_needing_split,
            "decoupling": activities_needing_decoupling
        },
        "recommendation": "Bruk /bulk/calculate-power eller /bulk/calculate-tss for å beregne manglende verdier"
    }

