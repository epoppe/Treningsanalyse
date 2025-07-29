from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from ..database.session import get_db
from ..services.power_service import PowerService
from ..storage import get_storage

router = APIRouter(prefix="/power", tags=["power"])

def get_power_service():
    storage = get_storage()
    return PowerService(storage)

@router.get("/activity/{activity_id}")
async def get_activity_power(
    activity_id: int,
    mass_kg: Optional[float] = Query(None, description="Løperens masse i kg (standard: 75kg)"),
    db: Session = Depends(get_db),
    power_service: PowerService = Depends(get_power_service)
):
    """
    Beregner power for en spesifikk løpeaktivitet.
    
    Args:
        activity_id: Aktivitetens ID
        mass_kg: Løperens masse i kg (valgfritt)
        
    Returns:
        Power-statistikk for aktiviteten
    """
    try:
        result = power_service.calculate_activity_power(activity_id, db, mass_kg)
        if result is None:
            raise HTTPException(status_code=404, detail="Could not calculate power for this activity")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating power: {str(e)}")

@router.get("/period")
async def get_period_power(
    start_date: str = Query(..., description="Startdato (YYYY-MM-DD)"),
    end_date: str = Query(..., description="Sluttdato (YYYY-MM-DD)"),
    mass_kg: Optional[float] = Query(None, description="Løperens masse i kg (standard: 75kg)"),
    db: Session = Depends(get_db),
    power_service: PowerService = Depends(get_power_service)
):
    """
    Beregner power-statistikk for alle løpeaktiviteter i en periode.
    
    Args:
        start_date: Startdato (YYYY-MM-DD)
        end_date: Sluttdato (YYYY-MM-DD)
        mass_kg: Løperens masse i kg (valgfritt)
        
    Returns:
        Power-statistikk for perioden
    """
    try:
        result = power_service.calculate_power_for_period(start_date, end_date, db, mass_kg)
        if result is None:
            raise HTTPException(status_code=500, detail="Error calculating power for period")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating power for period: {str(e)}")

@router.get("/info")
async def get_power_info():
    """
    Returnerer informasjon om power-beregningsparametere.
    
    Returns:
        Informasjon om power-beregning
    """
    return {
        "description": "Power-beregning for løpeaktiviteter basert på FIT-data",
        "parameters": {
            "mass_kg": "Løperens masse (standard: 75kg)",
            "speed_mps": "Hastighet i m/s",
            "grade_percent": "Stigning i prosent",
            "vertical_oscillation_cm": "Vertikal oscillasjon i cm",
            "stance_time_ms": "Ground contact time i ms",
            "wind_mps": "Vindhastighet i m/s (standard: 0)"
        },
        "calculation_components": [
            "Horisontal akselerasjon",
            "Vertikal arbeid fra terreng",
            "Vertikal arbeid fra oscillasjon",
            "Luftmotstand"
        ],
        "constants": {
            "air_density_kg_m3": 1.226,
            "aerodynamic_coefficient": 0.24,
            "gravity_m_s2": 9.81
        }
    }