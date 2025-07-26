"""
Training Readiness API Router.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
import logging

from ..database.session import get_db
from ..services.training_readiness_service import TrainingReadinessService

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Training Readiness"]
)

def get_training_readiness_service():
    """Dependency for TrainingReadinessService."""
    return TrainingReadinessService()

@router.get("/training-readiness")
async def get_training_readiness(
    target_date: Optional[date] = Query(None, description="Dato for training readiness (YYYY-MM-DD)"),
    service: TrainingReadinessService = Depends(get_training_readiness_service)
):
    """
    Hent training readiness score for en gitt dato.
    Hvis ingen dato er spesifisert, brukes dagens dato.
    """
    try:
        readiness = service.calculate_training_readiness(target_date)
        return readiness
    except Exception as e:
        logger.error(f"Feil ved henting av training readiness: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/training-readiness/weekly")
async def get_weekly_training_readiness(
    end_date: Optional[date] = Query(None, description="Sluttdato for uken (YYYY-MM-DD)"),
    service: TrainingReadinessService = Depends(get_training_readiness_service)
):
    """
    Hent training readiness for siste 7 dager.
    Hvis ingen sluttdato er spesifisert, brukes dagens dato.
    """
    try:
        weekly_readiness = service.get_weekly_readiness(end_date)
        return {
            "period": "weekly",
            "end_date": end_date.isoformat() if end_date else date.today().isoformat(),
            "data": weekly_readiness
        }
    except Exception as e:
        logger.error(f"Feil ved henting av ukentlig training readiness: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/training-readiness/status")
async def get_training_readiness_status(
    target_date: Optional[date] = Query(None, description="Dato for status (YYYY-MM-DD)"),
    service: TrainingReadinessService = Depends(get_training_readiness_service)
):
    """
    Hent kun readiness status og score for en gitt dato.
    """
    try:
        readiness = service.calculate_training_readiness(target_date)
        return {
            "date": readiness["date"],
            "total_score": readiness["total_score"],
            "readiness_status": readiness["readiness_status"],
            "recommendation": _get_recommendation(readiness["readiness_status"])
        }
    except Exception as e:
        logger.error(f"Feil ved henting av training readiness status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _get_recommendation(status: str) -> str:
    """Hent anbefaling basert på readiness status."""
    recommendations = {
        "optimal": "Du er klar for intensiv trening. Gå for det!",
        "good": "Du kan gjøre moderat til intensiv trening. Lytt til kroppen.",
        "moderate": "Gjør lett til moderat trening. Fokuser på teknikk og form.",
        "poor": "Gjør lett trening eller hvile. Prioriter recovery.",
        "very_poor": "Ta en hviledag. Fokuser på søvn og recovery.",
        "unknown": "Ikke nok data til å gi anbefaling."
    }
    return recommendations.get(status, "Ingen anbefaling tilgjengelig.") 