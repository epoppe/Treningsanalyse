from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from .services.garmin_client import GarminClient
from .storage import DataStorage
from .config import settings
import os
from pathlib import Path
import logging
from .database.session import SessionLocal
import garth

# Dependency for å hente en database sesjon
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_garmin_client(request: Request) -> GarminClient:
    """Henter den delte GarminClient-instansen fra app.state."""
    if not hasattr(request.app.state, 'garmin_client') or request.app.state.garmin_client is None:
        # Dette bør ideelt sett ikke skje hvis startup-eventet har kjørt og satt opp klienten.
        # Hvis det skjer, er Garmin-tjenesten ikke tilgjengelig.
        raise HTTPException(status_code=503, detail="Garmin Connect-tjenesten er ikke tilgjengelig eller ikke initialisert.")
    
    # Returner klienten selv om den ikke er autentisert - la API-endepunktene håndtere dette
    return request.app.state.garmin_client

async def get_data_storage(request: Request) -> DataStorage:
    """Henter den delte DataStorage-instansen fra app.state."""
    if not hasattr(request.app.state, 'data_storage'):
        # Storage bør alltid være tilgjengelig etter oppstart.
        raise HTTPException(status_code=500, detail="Lagringstjenesten er ikke tilgjengelig.")
    return request.app.state.data_storage 