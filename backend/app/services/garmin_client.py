from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
import json
import os
import time
import asyncio
import garth
import requests
from garth.exc import GarthException, GarthHTTPError
from pathlib import Path
import pandas as pd
import traceback
import logging
import uuid
import random
from dataclasses import asdict
from pydantic import BaseModel, ValidationError
from ..storage import DateTimeEncoder 
import shutil

# Pydantic-modeller for HRV-data
class HrvSummary(BaseModel):
    last_night_avg: Optional[int] = None
    last_night_5_min_high: Optional[int] = None
    weekly_avg: Optional[int] = None
    status: Optional[str] = None
    baseline_low_upper: Optional[int] = None
    baseline_balanced_lower: Optional[int] = None
    baseline_balanced_upper: Optional[int] = None

class HRVData(BaseModel):
    hrv_summary: Optional[HrvSummary] = None


# Oppdatert User-Agent for kompatibilitet med nyere Garmin API
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

# Patcher garth for å bruke oppdatert User-Agent
def patch_garth():
    """Applierer patch til garth-biblioteket for å bruke en nyere User-Agent."""
    garth.client.USER_AGENT = USER_AGENT

patch_garth()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GarminClient:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(GarminClient, cls).__new__(cls)
        return cls._instance

    def __init__(self, email: str, password: str, token_dir: str):
        self.email = email
        self.password = password
        self.token_dir = Path(token_dir)
        self.client_id = str(uuid.uuid4())
        self._initialized = False
        logger.info(f"GarminClient instance {self.client_id} __init__. Token directory: {self.token_dir}. Patches ensured.")
        
    async def initialize(self):
        """Initialiserer Garmin-klienten.
        
        Prøver først å gjenopprette en eksisterende sesjon. Hvis det feiler,
        utfører en ny pålogging og lagrer sesjonsinformasjonen.
        """
        logger.info(f"GarminClient instance {self.client_id} initialize. Initialiserer Garmin Client for {self.email}...")
        try:
            # Prøv først å gjenopprette eksisterende sesjon
            await asyncio.to_thread(garth.resume, str(self.token_dir))
            logger.info("Vellykket gjenoppretting av eksisterende Garmin-sesjon.")
            
            # Test at sesjonen fungerer
            try:
                await asyncio.to_thread(lambda: garth.client.username)
                logger.info("Sesjon bekreftet som gyldig.")
                self._initialized = True
                return True
            except GarthException:
                logger.info("Eksisterende sesjon er utløpt, utfører ny pålogging...")
                raise  # Trigger ny pålogging nedenfor
                
        except (GarthException, FileNotFoundError, Exception) as e:
            logger.info(f"Kunne ikke gjenopprette sesjon ({e}), utfører ny pålogging...")
            try:
                # Utfør ny pålogging
                await asyncio.to_thread(garth.login, self.email, self.password)
                # Lagre sesjonsinformasjon for fremtidig bruk
                await asyncio.to_thread(garth.save, str(self.token_dir))
                logger.info("Vellykket ny pålogging og lagring av sesjon.")
                self._initialized = True
                return True
            except GarthException as login_error:
                logger.error(f"Pålogging feilet: {login_error}")
                self._initialized = False
                return False

    def is_authenticated(self) -> bool:
        """Sjekker om en token-fil finnes i katalogen uten å gjøre et nettverkskall."""
        if not self.token_dir.exists():
            return False
        # Sjekker om det finnes noen .json-filer i token-katalogen
        for _ in self.token_dir.glob("*.json"):
            return True
        return False

    async def get_hrv_data(self, date: datetime) -> Optional[Dict[str, Any]]:
        """Henter HRV-data for en spesifikk dato."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente HRV-data.")
            return None
        try:
            date_str = date.strftime("%Y-%m-%d")
            logger.info(f"Henter HRV-data for {date_str}")
            hrv_data = await asyncio.to_thread(
                garth.connectapi, f"/hrv-service/hrv/daily/{date_str}"
            )
            # Validerer data med Pydantic-modellen
            validated_data = HRVData.model_validate(hrv_data)
            return validated_data.model_dump()
        except GarthHTTPError as e:
            if e.response.status_code == 404:
                logger.info(f"Ingen HRV-data funnet for {date_str}")
                return None
            logger.error(f"HTTP-feil ved henting av HRV-data for {date_str}: {e}")
            return None
        except ValidationError as e:
            logger.warning(f"Valideringsfeil for HRV-data på dato {date_str}: {e}. Data: {hrv_data}")
            return None # Returnerer None for å hoppe over ugyldig data
        except Exception as e:
            logger.error(f"En uventet feil oppstod under henting av HRV-data for {date_str}: {e}")
            logger.error(traceback.format_exc())
            return None



    # ... (resten av metodene i klassen forblir de samme) ...