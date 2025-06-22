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

# Dependency for å håndtere Garmin-klienten
_garmin_client_instance = None
async def get_garmin_client() -> GarminClient:
    """
    Dependency to get a properly initialized GarminClient instance.
    Handles singleton pattern and async initialization.
    """
    global _garmin_client_instance
    
    # Opprett instans hvis den ikke finnes
    if _garmin_client_instance is None:
        _garmin_client_instance = GarminClient(
            email=settings.GARMIN_EMAIL,
            password=settings.GARMIN_PASSWORD,
            token_dir=settings.TOKEN_DIR
        )
    
    # Initialiser (eller re-initialiser) hvis klienten ikke er logget inn
    if not getattr(garth.client, "username", None):
        try:
            await _garmin_client_instance.initialize()
        except Exception as e:
            logging.error(f"Kunne ikke initialisere Garmin-klienten: {e}")
            raise HTTPException(
                status_code=503, 
                detail="Kunne ikke koble til Garmin Connect."
            )
            
    return _garmin_client_instance

_data_storage_instance = None
def get_data_storage() -> DataStorage:
    global _data_storage_instance
    if _data_storage_instance is None:
        _data_storage_instance = DataStorage(data_dir=settings.DATA_DIR)
    return _data_storage_instance 