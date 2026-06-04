"""
Training Readiness API Router.
Includes chat endpoint for readiness questions.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
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
    response: Response,
    target_date: Optional[date] = Query(None, description="Dato for training readiness (YYYY-MM-DD)"),
    service: TrainingReadinessService = Depends(get_training_readiness_service)
):
    """
    Hent training readiness score for en gitt dato.
    Hvis ingen dato er spesifisert, brukes dagens dato.
    """
    # Disable caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
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


class ChatRequest(BaseModel):
    message: str
    date: str  # YYYY-MM-DD


@router.post("/training-readiness/chat")
async def readiness_chat(
    body: ChatRequest,
    service: TrainingReadinessService = Depends(get_training_readiness_service)
):
    """
    Chat-endepunkt som svarer på spørsmål om training readiness for en gitt dato.
    Bruker readiness-data til å gi relevante svar uten ekstern LLM.
    """
    try:
        target = date.fromisoformat(body.date) if body.date else date.today()
        readiness = service.calculate_training_readiness(target)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ugyldig datoformat (bruk YYYY-MM-DD)")
    except Exception as e:
        logger.error(f"Feil ved henting av readiness for chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    msg = body.message.lower().strip()
    score = readiness.get("total_score", 0)
    status = readiness.get("readiness_status", "unknown")
    components = readiness.get("components", {})
    rec = _get_recommendation(status)

    # Søvn-relatert
    if any(k in msg for k in ["søvn", "sleep", "sovn"]):
        s = components.get("sleep_score")
        if s is not None:
            return {"response": f"Søvnscore for {body.date} er {round(s)}/100. " + (
                "God søvnkvalitet." if s >= 70 else
                "Moderat søvn." if s >= 50 else
                "Søvn kan forbedres – prioriter recovery."
            )}
        return {"response": "Ingen søvndata tilgjengelig for denne datoen."}

    # HRV-relatert
    if any(k in msg for k in ["hrv", "hjerte", "heart"]):
        s = components.get("hrv_score")
        if s is not None:
            return {"response": f"HRV-score er {round(s)}/100. " + (
                "HRV er innenfor normalt område." if s >= 70 else
                "HRV kan indikere økt stress eller tretthet." if s >= 50 else
                "Lav HRV – vurder hvile og recovery."
            )}
        return {"response": "Ingen HRV-data tilgjengelig for denne datoen."}

    # Form/TSB
    if any(k in msg for k in ["form", "tsb", "fatigue", "utmattelse"]):
        s = components.get("form_score")
        if s is not None:
            return {"response": f"Form/TSB-score er {round(s)}/100. " + rec}
        return {"response": f"Form-data ikke tilgjengelig. Anbefaling: {rec}"}

    # Generell readiness / klar / anbefaling
    if any(k in msg for k in ["klar", "ready", "anbefal", "anbefaling", "trening", "tren", "hva", "hvordan", "er jeg"]):
        return {"response": (
            f"Readiness for {body.date}: {round(score)}/100 ({status}). {rec} "
            f"Komponenter: Søvn {round(components.get('sleep_score', 0))}, "
            f"HRV {round(components.get('hrv_score', 0))}, Form {round(components.get('form_score', 0))}."
        )}

    # Standard
    return {"response": f"Readiness-score: {round(score)}/100. {rec}"} 
