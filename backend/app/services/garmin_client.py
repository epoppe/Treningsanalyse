import asyncio
import logging
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import garth
from garth.exc import GarthException, GarthHTTPError
from pydantic import BaseModel

# Sett opp logging tidlig så den er tilgjengelig
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prøv å importere garth's HRV-klasser hvis tilgjengelige
try:
    DailyHRV = getattr(garth, 'DailyHRV', None)
    HRVData = getattr(garth, 'HRVData', None)
except ImportError as e:
    DailyHRV = None
    HRVData = None
    logger.warning(f"Kunne ikke importere HRV-klasser fra garth: {e} - bruker kun API-kall")

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

    async def get_activities(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Henter aktiviteter for en gitt periode."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente aktiviteter.")
            return []
        
        try:
            # Konverter datoer til strenger som Garmin API forventer
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            
            logger.info(f"Henter aktiviteter fra Garmin API: {start_str} til {end_str}")
            
            # Hent aktiviteter fra Garmin Connect API
            activities = await asyncio.to_thread(
                garth.connectapi, 
                f"/activitylist-service/activities/search/activities?startDate={start_str}&endDate={end_str}"
            )
            
            if isinstance(activities, list):
                logger.info(f"Hentet {len(activities)} aktiviteter fra Garmin")
                return activities
            else:
                logger.warning("Uventet respons fra Garmin API - ikke en liste")
                return []
                
        except GarthHTTPError as e:
            logger.error(f"HTTP-feil ved henting av aktiviteter: {e}")
            return []
        except Exception as e:
            logger.error(f"Feil ved henting av aktiviteter: {e}")
            logger.error(traceback.format_exc())
            return []

    async def get_activity_details(self, activity_id: str) -> Optional[bytes]:
        """Henter detaljerte data (FIT-fil) for en aktivitet."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente aktivitetsdetaljer.")
            return None
        
        try:
            logger.info(f"Henter detaljer for aktivitet {activity_id}")
            
            # Hent FIT-fil fra Garmin Connect API
            fit_data = await asyncio.to_thread(
                garth.download, 
                f"/download-service/files/activity/{activity_id}"
            )
            
            if isinstance(fit_data, bytes):
                logger.info(f"Hentet FIT-data for aktivitet {activity_id} ({len(fit_data)} bytes)")
                return fit_data
            else:
                logger.warning(f"Uventet respons ved henting av FIT-data for aktivitet {activity_id}")
                return None
                
        except GarthHTTPError as e:
            # Sjekk om det er en 404-feil (ingen data funnet)
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info(f"Ingen FIT-data funnet for aktivitet {activity_id}")
                return None
            logger.error(f"HTTP-feil ved henting av FIT-data for aktivitet {activity_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Feil ved henting av FIT-data for aktivitet {activity_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    async def get_hrv_data_alternative(self, date: datetime) -> Optional[Dict[str, Any]]:
        """Alternativ implementasjon som bruker garth's innebygde HRV-funksjonalitet."""
        if not self.is_authenticated():
            logger.error("Ikke autentiseret. Kan ikke hente HRV-data.")
            return None
        
        date_obj = date.date()
        date_str = date.strftime("%Y-%m-%d")
        logger.info(f"Henter HRV-data (alternativ metode) for {date_str}")
        
        # Debugging: List alle garth-attributter og metoder
        garth_attrs = [attr for attr in dir(garth) if 'HRV' in attr or 'hrv' in attr]
        logger.info(f"Garth HRV-relaterte attributter: {garth_attrs}")
        logger.info(f"Garth HRV klasser tilgjengelig: DailyHRV={DailyHRV is not None}, HRVData={HRVData is not None}")
        
        if DailyHRV:
            logger.info(f"DailyHRV metoder: {[m for m in dir(DailyHRV) if not m.startswith('_')]}")
        if HRVData:
            logger.info(f"HRVData metoder: {[m for m in dir(HRVData) if not m.startswith('_')]}")
        
        # Prøv flere garth-metoder i prioritert rekkefølge
        methods_to_try = []
        
        if DailyHRV is not None and hasattr(DailyHRV, 'list'):
            methods_to_try.append(("DailyHRV.list", lambda: DailyHRV.list(date_str, 1)))
        
        if HRVData is not None and hasattr(HRVData, 'get'):
            methods_to_try.append(("HRVData.get", lambda: HRVData.get(date_str)))
            
        if HRVData is not None and hasattr(HRVData, 'list'):
            methods_to_try.append(("HRVData.list", lambda: HRVData.list(date_str, 1)))
        
        # Prøv også direct garth calls
        methods_to_try.append(("garth.DailyHRV.list", lambda: garth.DailyHRV.list(date_str, 1)))
        
        for method_name, method_func in methods_to_try:
            try:
                logger.info(f"Prøver {method_name} for {date_str}")
                hrv_data = await asyncio.to_thread(method_func)
                
                if hrv_data:
                    logger.info(f"HRV-data funnet med {method_name} for {date_str}: {hrv_data}")
                    
                    # Håndter ulike returformater
                    if isinstance(hrv_data, list) and len(hrv_data) > 0:
                        # DailyHRV.list returnerer liste
                        hrv_item = hrv_data[0]
                        if hasattr(hrv_item, 'last_night_avg'):
                            hrv_dict = {
                                "hrv_summary": {
                                    "last_night_avg": hrv_item.last_night_avg,
                                    "last_night_5_min_high": getattr(hrv_item, 'last_night_5_min_high', None),
                                    "weekly_avg": getattr(hrv_item, 'weekly_avg', None),
                                    "status": getattr(hrv_item, 'status', None),
                                    "baseline_low_upper": getattr(hrv_item, 'baseline_low_upper', None) if hasattr(hrv_item, 'baseline') and hrv_item.baseline else None,
                                    "baseline_balanced_lower": getattr(hrv_item, 'baseline_balanced_lower', None) if hasattr(hrv_item, 'baseline') and hrv_item.baseline else None,
                                    "baseline_balanced_upper": getattr(hrv_item, 'baseline_balanced_upper', None) if hasattr(hrv_item, 'baseline') and hrv_item.baseline else None,
                                }
                            }
                            return hrv_dict
                    elif hasattr(hrv_data, 'hrv_summary'):
                        # HRVData.get returnerer objekt med hrv_summary
                        hrv_dict = {
                            "hrv_summary": {
                                "last_night_avg": hrv_data.hrv_summary.last_night_avg if hrv_data.hrv_summary else None,
                                "last_night_5_min_high": hrv_data.hrv_summary.last_night_5_min_high if hrv_data.hrv_summary else None,
                                "weekly_avg": hrv_data.hrv_summary.weekly_avg if hrv_data.hrv_summary else None,
                                "status": hrv_data.hrv_summary.status if hrv_data.hrv_summary else None,
                                "baseline_low_upper": hrv_data.hrv_summary.baseline.low_upper if hrv_data.hrv_summary and hrv_data.hrv_summary.baseline else None,
                                "baseline_balanced_lower": hrv_data.hrv_summary.baseline.balanced_low if hrv_data.hrv_summary and hrv_data.hrv_summary.baseline else None,
                                "baseline_balanced_upper": hrv_data.hrv_summary.baseline.balanced_upper if hrv_data.hrv_summary and hrv_data.hrv_summary.baseline else None,
                            }
                        }
                        return hrv_dict
                        
                logger.info(f"{method_name} returnerte data men i ukjent format for {date_str}")
                        
            except Exception as e:
                logger.debug(f"{method_name} feilet for {date_str}: {e}")
                continue
        
        logger.info(f"Ingen av garth-metodene fant HRV-data for {date_str}, faller tilbake til API-kall")
        return await self.get_hrv_data(date)

    async def get_hrv_data(self, date: datetime) -> Optional[Dict[str, Any]]:
        """Henter HRV-data for en spesifikk dato."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente HRV-data.")
            return None
        try:
            date_str = date.strftime("%Y-%m-%d")
            logger.info(f"Henter HRV-data for {date_str}")
            
            # Prøv først standard API-endepunkt
            try:
                hrv_data = await asyncio.to_thread(
                    garth.connectapi, f"/hrv-service/hrv/daily/{date_str}"
                )
            except GarthHTTPError as api_error:
                logger.info(f"Standard HRV API feilet for {date_str}, prøver alternative endepunkter: {api_error}")
                hrv_data = None
                
                # Prøv flere alternative API-endepunkter
                alternative_endpoints = [
                    # Prøv DailyHRV endpoint som garth bruker
                    (f"/usersummary-service/stats/hrv/daily/{date_str}", {}),
                    # Prøv wellness endpoint
                    (f"/usersummary-service/usersummary/daily/{garth.client.username}", {"calendarDate": date_str}),
                    # Prøv direkte wellness HRV endpoint
                    (f"/wellness-service/wellness/dailyHRV/{garth.client.username}", {"date": date_str}),
                ]
                
                for endpoint, params in alternative_endpoints:
                    try:
                        logger.info(f"Prøver alternativt endepunkt: {endpoint} med params: {params}")
                        alt_data = await asyncio.to_thread(
                            garth.connectapi, endpoint, params=params
                        )
                        logger.debug(f"Alternativt endepunkt {endpoint} returnerte: {alt_data}")
                        
                        if alt_data:
                            # Prøv å trekke ut HRV-data fra ulike responsformater
                            if 'allMetrics' in alt_data:
                                # Format fra usersummary endpoint
                                hrv_metrics = alt_data.get('allMetrics', {}).get('metricsMap', {}).get('WELLNESS_HRV_RMSSD', {})
                                if hrv_metrics and hrv_metrics.get('value'):
                                    hrv_data = {
                                        "hrv_summary": {
                                            "last_night_avg": hrv_metrics.get('value'),
                                            "last_night_5_min_high": None,
                                            "weekly_avg": None,
                                            "status": None,
                                            "baseline_low_upper": None,
                                            "baseline_balanced_lower": None,
                                            "baseline_balanced_upper": None,
                                        }
                                    }
                                    logger.info(f"Hentet HRV-data fra usersummary endpoint for {date_str}: {hrv_data}")
                                    break
                            elif 'hrvSummary' in alt_data:
                                # Format fra wellness endpoint
                                hrv_data = {"hrv_summary": alt_data['hrvSummary']}
                                logger.info(f"Hentet HRV-data fra wellness endpoint for {date_str}: {hrv_data}")
                                break
                            elif isinstance(alt_data, dict) and any(key in alt_data for key in ['last_night_avg', 'weekly_avg']):
                                # Direkte HRV format
                                hrv_data = {"hrv_summary": alt_data}
                                logger.info(f"Hentet HRV-data i direkte format for {date_str}: {hrv_data}")
                                break
                                
                    except Exception as alt_error:
                        logger.debug(f"Alternativt endepunkt {endpoint} feilet: {alt_error}")
                        continue
                
                if not hrv_data:
                    logger.info(f"Ingen HRV-data funnet i noen av de alternative endepunktene for {date_str}")
                    return None
            
            # Logg rå data for debugging
            logger.debug(f"Rå HRV-data for {date_str}: {hrv_data}")
            
            # Sjekk om data er tomt eller None
            if not hrv_data:
                logger.info(f"Tomt HRV-data-svar for {date_str}")
                return None
            
            # Validerer data med Pydantic-modellen
            validated_data = HRVData.model_validate(hrv_data)
            logger.info(f"Validerte HRV-data for {date_str}: {validated_data.model_dump()}")
            return validated_data.model_dump()
        except GarthHTTPError as e:
            # Denne catch-blokken håndterer bare feil som ikke ble håndtert i try-blokken over
            logger.info(f"GarthHTTPError ved henting av HRV-data for {date_str}: {e}")
            # Sjekk om det er en 404-feil (ingen data funnet)
            if "404" in str(e) or "not found" in str(e).lower():
                logger.info(f"Ingen HRV-data funnet for {date_str} (404 Not Found)")
                return None
            logger.error(f"HTTP-feil ved henting av HRV-data for {date_str}: {e}")
            return None
        except Exception as e:
            logger.error(f"En uventet feil oppstod under henting av HRV-data for {date_str}: {e}")
            logger.error(traceback.format_exc())
            return None