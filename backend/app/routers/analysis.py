from fastapi import APIRouter, Depends, Query
from typing import Optional
from ..services.analysis_service import AnalysisService
from ..storage import DataStorage
from ..dependencies import get_data_storage

# Definerer router for analyse-endepunkter
router = APIRouter()

@router.get("/running-economy/{activity_id}")
def get_running_economy_analysis(
    activity_id: int,
    storage: DataStorage = Depends(get_data_storage)
):
    """Henter og analyserer løpsøkonomi for en aktivitet."""
    analysis_service = AnalysisService(storage)
    return analysis_service.get_running_economy(activity_id)

@router.get("/training-load")
def get_training_load_analysis(
    storage: DataStorage = Depends(get_data_storage)
):
    """Henter og analyserer treningsbelastning (TSS) over tid."""
    analysis_service = AnalysisService(storage)
    return analysis_service.get_training_load()

@router.get("/hrv")
def get_hrv_analysis(
    storage: DataStorage = Depends(get_data_storage),
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format")
):
    """Henter og analyserer HRV-data over tid."""
    analysis_service = AnalysisService(storage)
    return analysis_service.get_hrv_over_time(start_date, end_date)
