from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.orm import Session
from ..services.analysis_service import AnalysisService
from ..storage import DataStorage
from ..dependencies import get_data_storage, get_db
from ..database.models.activity import Activity

# Definerer router for analyse-endepunkter
router = APIRouter()

@router.get("/running-economy/{activity_id}")
def get_running_economy_analysis(
    activity_id: int,
    storage: DataStorage = Depends(get_data_storage),
    db: Session = Depends(get_db)
):
    """Henter og analyserer løpsøkonomi for en aktivitet med caching."""
    # Sjekk først cache i databasen
    activity = db.query(Activity).filter(Activity.id == str(activity_id)).first()
    if not activity:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Activity not found")
    
    # Hvis løpsøkonomi allerede er beregnet og lagret, returner cache
    if activity.running_economy is not None:
        return {
            "activity_id": activity_id,
            "running_economy": round(activity.running_economy, 2),
            "calculation_method": "cached"
        }
    
    # Beregn løpsøkonomi fra AnalysisService
    analysis_service = AnalysisService(storage)
    result = analysis_service.get_running_economy(activity_id)
    
    # Lagre resultatet i databasen hvis beregning var vellykket
    if result and "running_economy" in result and result["running_economy"] is not None:
        try:
            activity.running_economy = result["running_economy"]
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Kunne ikke lagre løpsøkonomi for aktivitet {activity_id}: {e}")
    
    return result

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
