from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..dependencies import get_data_storage, get_garmin_client
from ..storage import DataStorage
from ..services.garmin_client import GarminClient

router = APIRouter()

class ActivityResponse(BaseModel):
    activities: List[Dict[str, Any]]
    count: int

@router.get("/activities", response_model=ActivityResponse)
async def read_activities(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    storage: DataStorage = Depends(get_data_storage)
):
    """Henter lagrede aktiviteter, med valgfri filtrering på dato."""
    try:
        activities = storage.get_activities(start_date=start_date, end_date=end_date)
        return {"activities": activities, "count": len(activities)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/activities/{activity_id}/details", response_model=List[Dict[str, Any]])
async def read_activity_details(
    activity_id: int,
    storage: DataStorage = Depends(get_data_storage),
    garmin_client: GarminClient = Depends(get_garmin_client)
):
    """
    Henter detaljerte tidsseriedata for en aktivitet.
    Sjekker først lokal lagring. Hvis data ikke finnes, hentes de fra Garmin.
    """
    try:
        # 1. Sjekk lokal lagring først
        details = storage.get_activity_details(activity_id)
        if details:
            return details

        # 2. Hvis ikke lokalt, hent fra Garmin
        fit_data = await garmin_client.get_activity_details(str(activity_id))
        if not fit_data:
            raise HTTPException(status_code=404, detail="Kunne ikke hente aktivitetsdetaljer fra Garmin.")

        # 3. Lagre dataene lokalt
        storage.save_activity_details(activity_id, fit_data)

        # 4. Hent og returner de nylig lagrede dataene
        new_details = storage.get_activity_details(activity_id)
        if new_details:
            return new_details
        else:
            # Dette skal i teorien ikke skje hvis lagring var vellykket
            raise HTTPException(status_code=500, detail="Klarte ikke å hente data etter lagring.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"En feil oppstod: {str(e)}")
