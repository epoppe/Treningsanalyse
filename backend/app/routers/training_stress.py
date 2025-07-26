from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, timedelta
import logging

from ..database.session import get_db
from ..services.training_stress_service import TrainingStressService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/training-stress",
    tags=["Training Stress Score"]
)

@router.get("/test")
def test_training_stress():
    """Test endpoint for å sjekke om routeren fungerer."""
    return {"message": "Training Stress router fungerer", "status": "ok"}

@router.get("/summary")
def get_training_stress_summary(
    days: int = Query(30, description="Antall dager tilbake i tid"),
    db: Session = Depends(get_db)
):
    """Hent sammendrag av Training Stress Score for siste N dager."""
    try:
        # Test enkel database-tilgang først
        from ..database.models.activity import Activity
        activity_count = db.query(Activity).count()
        
        logger.info(f"Database-tilgang fungerer. Fant {activity_count} aktiviteter totalt")
        
        # Test import av TrainingStressService
        try:
            from ..services.training_stress_service import TrainingStressService
            logger.info("TrainingStressService import fungerer")
        except Exception as import_error:
            logger.error(f"Feil ved import av TrainingStressService: {import_error}")
            raise HTTPException(status_code=500, detail=f"Import feil: {str(import_error)}")
        
        service = TrainingStressService(db)
        result = service.get_training_load_summary(days)
        
        if result["data"] is None:
            raise HTTPException(status_code=404, detail=result["message"])
        
        return result
        
    except Exception as e:
        logger.error(f"Feil ved henting av Training Stress summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Intern serverfeil: {str(e)}")

@router.get("/metrics")
def get_training_stress_metrics(
    start_date: date = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Hent detaljerte Training Stress Score metrics for en periode."""
    try:
        # Test enkel database-tilgang først
        from ..database.models.activity import Activity
        activity_count = db.query(Activity).count()
        
        logger.info(f"Database-tilgang fungerer. Fant {activity_count} aktiviteter totalt")
        
        # Test import av TrainingStressService
        try:
            from ..services.training_stress_service import TrainingStressService
            logger.info("TrainingStressService import fungerer")
        except Exception as import_error:
            logger.error(f"Feil ved import av TrainingStressService: {import_error}")
            raise HTTPException(status_code=500, detail=f"Import feil: {str(import_error)}")
        
        service = TrainingStressService(db)
        
        # Bruk den enkle calculate_training_load_metrics_simple metoden
        result = service.calculate_training_load_metrics_simple(start_date, end_date)
        
        if result["data"] is None:
            raise HTTPException(status_code=404, detail=result["message"])
        
        return result
        
    except Exception as e:
        logger.error(f"Feil ved henting av Training Stress metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Intern serverfeil: {str(e)}")

@router.get("/activity/{activity_id}")
def get_activity_tss(
    activity_id: str,
    db: Session = Depends(get_db)
):
    """Beregn TSS for en spesifikk aktivitet."""
    try:
        from ..database.models.activity import Activity
        
        activity = db.query(Activity).filter(Activity.activity_id == activity_id).first()
        if not activity:
            raise HTTPException(status_code=404, detail="Aktivitet ikke funnet")
        
        service = TrainingStressService(db)
        tss = service.calculate_tss_for_activity(activity)
        
        return {
            "activity_id": activity_id,
            "activity_name": activity.activity_name,
            "date": activity.start_time.date().isoformat(),
            "duration": activity.duration,
            "distance": activity.distance,
            "tss": tss,
            "training_effect": activity.total_training_effect,
            "anaerobic_training_effect": activity.total_anaerobic_training_effect,
            "average_heart_rate": activity.average_heart_rate,
            "vo2_max": activity.vo2_max
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feil ved beregning av TSS for aktivitet {activity_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Intern serverfeil: {str(e)}")

@router.get("/recent-activities")
def get_recent_activities_tss(
    limit: int = Query(20, description="Antall aktiviteter å hente"),
    db: Session = Depends(get_db)
):
    """Hent TSS for de nyeste aktivitetene."""
    try:
        from ..database.models.activity import Activity
        from sqlalchemy import desc
        
        activities = db.query(Activity).order_by(desc(Activity.start_time)).limit(limit).all()
        
        if not activities:
            raise HTTPException(status_code=404, detail="Ingen aktiviteter funnet")
        
        service = TrainingStressService(db)
        results = []
        
        for activity in activities:
            tss = service.calculate_tss_for_activity(activity)
            results.append({
                "activity_id": activity.activity_id,
                "activity_name": activity.activity_name,
                "date": activity.start_time.date().isoformat(),
                "duration": activity.duration,
                "distance": activity.distance,
                "tss": tss,
                "training_effect": activity.total_training_effect,
                "anaerobic_training_effect": activity.total_anaerobic_training_effect,
                "average_heart_rate": activity.average_heart_rate,
                "activity_type": activity.activity_type.type_key if activity.activity_type else None
            })
        
        return {
            "activities": results,
            "total_count": len(results)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feil ved henting av nyeste aktiviteter TSS: {e}")
        raise HTTPException(status_code=500, detail=f"Intern serverfeil: {str(e)}") 