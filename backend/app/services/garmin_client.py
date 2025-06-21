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
from ..storage import DateTimeEncoder  # Importer DateTimeEncoder fra storage
import shutil

# Oppdatert User-Agent for kompatibilitet med nyere Garmin API
garth.http.USER_AGENT = {"User-Agent": "GCM-iOS-5.7.2.1"}

logger = logging.getLogger(__name__)

# Forenklet patching - kun for kritiske problemer
_patches_applied_flag = False

def ensure_garth_patches():
    """Anvend kun nødvendige patches for Garth 0.5.16 kompatibilitet."""
    global _patches_applied_flag
    if _patches_applied_flag:
        return
    
    logger.info("ensure_garth_patches: Applierer minimale garth patches for versjon 0.5.16...")
    _patches_applied_flag = True
    logger.info("Garth patches anvendt.")

class RateLimitExceeded(Exception):
    """Spesiell unntaksklasse for rate limiting"""
    pass

class GarminClient:
    def __init__(self, email: str, password: str, token_dir: str = "tokens"):
        ensure_garth_patches()
        
        self.email = email
        self.password = password
        self.token_dir = token_dir
        self._token_file = os.path.join(self.token_dir, "garmin_token")
        self._is_authenticated = False
        self._instance_id = str(uuid.uuid4())
        
        # Opprett token-katalog hvis den ikke eksisterer
        os.makedirs(self.token_dir, exist_ok=True)
        
        logger.info(f"GarminClient instance {self._instance_id} __init__. Token directory: {token_dir}. Patches ensured.")

    async def initialize(self) -> bool:
        """Initialiserer Garmin-klienten med forbedret rate-limiting håndtering."""
        logger.info(f"GarminClient instance {self._instance_id} initialize. Initialiserer Garmin Client for {self.email} ved hjelp av garth-biblioteket.")
        
        try:
            # Prøv først å laste eksisterende sesjon
            if await self._attempt_load_session_from_token():
                logger.info("Vellykket innlasting av eksisterende sesjon.")
                self._is_authenticated = True
                return True
            
            # Sjekk om vi har for mange nylige påloggingsforsøk
            if self._should_skip_login_due_to_rate_limit():
                logger.warning("Hopper over pålogging på grunn av nylige rate-limit problemer. Prøv igjen senere.")
                return False
            
            # Utfør nye påloggingsforsøk med forbedret håndtering
            if await self._perform_new_login_attempts():
                self._is_authenticated = True
                return True
            else:
                logger.error("Kunne ikke autentisere med Garmin Connect.")
                return False
                
        except Exception as e:
            logger.critical(f"Alvorlig uventet feil under initialisering av Garmin Client: {e}")
            logger.debug(traceback.format_exc())
            return False

    def _should_skip_login_due_to_rate_limit(self) -> bool:
        """Sjekker om vi skal hoppe over pålogging på grunn av nylige rate-limit problemer."""
        rate_limit_file = os.path.join(self.token_dir, "rate_limit_info.json")
        
        if not os.path.exists(rate_limit_file):
            return False
        
        try:
            with open(rate_limit_file, 'r') as f:
                rate_limit_info = json.load(f)
            
            last_attempt = datetime.fromisoformat(rate_limit_info.get('last_attempt', '2000-01-01'))
            consecutive_failures = rate_limit_info.get('consecutive_failures', 0)
            
            # Hvis vi har hatt mange påfølgende feil, vent lenger
            if consecutive_failures >= 3:
                hours_to_wait = min(24, 2 ** (consecutive_failures - 3))  # Eksponentiell backoff, maks 24 timer
                if datetime.now() - last_attempt < timedelta(hours=hours_to_wait):
                    logger.info(f"Venter {hours_to_wait} timer mellom påloggingsforsøk på grunn av rate-limiting.")
                    return True
            
            return False
        except Exception as e:
            logger.warning(f"Kunne ikke lese rate-limit info: {e}")
            return False

    def _update_rate_limit_info(self, success: bool):
        """Oppdaterer informasjon om rate-limiting."""
        rate_limit_file = os.path.join(self.token_dir, "rate_limit_info.json")
        
        try:
            if os.path.exists(rate_limit_file):
                with open(rate_limit_file, 'r') as f:
                    rate_limit_info = json.load(f)
            else:
                rate_limit_info = {}
            
            rate_limit_info['last_attempt'] = datetime.now().isoformat()
            
            if success:
                rate_limit_info['consecutive_failures'] = 0
            else:
                rate_limit_info['consecutive_failures'] = rate_limit_info.get('consecutive_failures', 0) + 1
            
            with open(rate_limit_file, 'w') as f:
                json.dump(rate_limit_info, f)
                
        except Exception as e:
            logger.warning(f"Kunne ikke oppdatere rate-limit info: {e}")

    async def _attempt_load_session_from_token(self) -> bool:
        """Forsøker å laste inn sesjon fra eksisterende token-katalog."""
        if not os.path.exists(self._token_file):
            logger.info(f"Token-mappe {self._token_file} ikke funnet. Fortsetter direkte til pålogging.")
            return False
        
        try:
            await asyncio.to_thread(garth.resume, self._token_file)
            
            # Verifiser at sesjonen fungerer
            if hasattr(garth.client, 'username') and garth.client.username:
                logger.info(f"Vellykket innlasting av sesjon for bruker: {garth.client.username}")
                return True
            else:
                logger.warning("Sesjon lastet, men ingen brukerinformasjon funnet.")
                return False
                
        except Exception as e:
            logger.warning(f"Kunne ikke laste sesjon fra token: {e}")
            return False

    async def _perform_new_login_attempts(self) -> bool:
        """Utfører nye påloggingsforsøk med forbedret rate-limiting håndtering."""
        max_attempts = 2  # Redusert fra 3 for å unngå for mange forsøk
        base_delay = 60   # Økt til 60 sekunder
        max_delay = 600   # Maksimal ventetid på 10 minutter
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"Påloggingsforsøk {attempt + 1}/{max_attempts}...")
                
                # Slett eksisterende token-katalog hvis den eksisterer
                if os.path.exists(self._token_file):
                    shutil.rmtree(self._token_file, ignore_errors=True)
                
                # Utfør pålogging
                await asyncio.to_thread(garth.login, self.email, self.password)
                
                # Lagre tokens
                await asyncio.to_thread(garth.save, self._token_file)
                
                logger.info("Vellykket pålogging og lagring av tokens.")
                self._update_rate_limit_info(success=True)
                return True
                
            except (GarthHTTPError, requests.exceptions.HTTPError) as e:
                if hasattr(e, 'response') and e.response.status_code == 429:
                    # Rate limit nådd
                    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 30), max_delay)
                    logger.warning("Rate limit nådd. Venting før neste forsøk...")
                    logger.info(f"Venting {delay:.1f} sekunder før neste forsøk...")
                    
                    if attempt < max_attempts - 1:  # Ikke vent etter siste forsøk
                        await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"HTTP-feil under pålogging: {e}")
                    break
                    
            except Exception as e:
                logger.error(f"Uventet feil under pålogging: {e}")
                break
        
        logger.error("Kunne ikke logge inn etter flere forsøk")
        self._update_rate_limit_info(success=False)
        return False

    def is_authenticated(self) -> bool:
        """Sjekker om klienten er autentisert."""
        return self._is_authenticated and hasattr(garth.client, 'oauth1_token') and garth.client.oauth1_token is not None

    async def get_activities(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Henter aktiviteter fra Garmin Connect."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente aktiviteter.")
            return []
        
        try:
            logger.info(f"Henter aktiviteter fra {start_date} til {end_date} med garth.connectapi")
            
            activities = await asyncio.to_thread(
                garth.connectapi,
                "/activitylist-service/activities/search/activities",
                params={
                    "startDate": start_date.strftime("%Y-%m-%d"),
                    "endDate": end_date.strftime("%Y-%m-%d"),
                    "limit": 100
                }
            )
            
            if activities and isinstance(activities, list):
                logger.info(f"Hentet {len(activities)} aktiviteter fra Garmin Connect.")
                logger.debug(f"Aktivitetsdata: {json.dumps(activities[:2], cls=DateTimeEncoder, indent=2)}")
                return activities
            else:
                logger.info("Ingen aktiviteter funnet i det angitte tidsrommet.")
                return []
                
        except AssertionError as e:
            if "OAuth1 token is required" in str(e):
                logger.error("OAuth1 token mangler. Autentisering kreves.")
                self._is_authenticated = False
            else:
                logger.error(f"Assertion error under API-kall: {e}")
            return []
            
        except Exception as e:
            logger.error(f"Feil under API-kall: {e}")
            logger.debug(traceback.format_exc())
            return []

    async def get_activity_details(self, activity_id: str) -> Optional[bytes]:
        """Laster ned detaljerte data for en enkelt aktivitet i .fit-format."""
        if not self.is_authenticated():
            logger.error("Ikke autentisert. Kan ikke hente aktivitetsdetaljer.")
            return None
        
        try:
            logger.info(f"Laster ned FIT-fil for aktivitet {activity_id}")
            fit_data = await asyncio.to_thread(
                garth.download,
                f"/download-service/files/activity/{activity_id}"
            )
            
            if fit_data:
                logger.info(f"FIT-fil for aktivitet {activity_id} lastet ned ({len(fit_data)} bytes).")
                return fit_data
            else:
                logger.warning(f"Ingen FIT-data mottatt for aktivitet {activity_id}.")
                return None
        except Exception as e:
            logger.error(f"Kunne ikke laste ned FIT-fil for aktivitet {activity_id}: {e}", exc_info=True)
            return None

    def create_manual_token_instructions(self) -> str:
        """Genererer instruksjoner for manuell token-opprettelse."""
        return f"""
        MANUELL TOKEN-OPPSETT:
        
        På grunn av Garmin's strenge rate-limiting, kan du sette opp tokens manuelt:
        
        1. Installer garth på din lokale maskin: pip install garth
        2. Kjør følgende Python-kode lokalt:
        
        import garth
        garth.login("din_email", "ditt_passord")
        garth.save("{self._token_file}")
        
        3. Kopier hele '{self._token_file}' katalogen til backend/tokens/
        4. Start serveren på nytt
        
        Dette vil unngå rate-limiting problemer.
        """

    async def get_sleep_data(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Hent søvndata mellom to datoer ved hjelp av garth.SleepData.list()."""
        try:
            logger.info(f"Henter søvndata fra {start_date} til {end_date} med garth.SleepData.list")
            
            await self._wait_for_rate_limit()
            
            # Beregn antall dager
            delta = end_date - start_date
            period_days = delta.days + 1
            
            # garth.SleepData.list() er blokkerende
            sleep_data_pydantic = await asyncio.to_thread(
                garth.SleepData.list,
                start_date.strftime("%Y-%m-%d"),
                period_days
            )
            
            if not sleep_data_pydantic:
                logger.info("Ingen søvndata funnet for den angitte perioden.")
                return []

            # Konverter Pydantic-objekter til dicts
            result_list = []
            for item in sleep_data_pydantic:
                if hasattr(item, 'model_dump'):
                    result_list.append(item.model_dump(mode='json'))
                else:
                    logger.warning(f"Element i listen fra garth.SleepData.list er ikke et Pydantic-objekt: {item}")
                    result_list.append(item)
            
            logger.info(f"Hentet {len(result_list)} søvnregistreringer.")
            return result_list
            
        except GarthException as e:
            logger.error(f"Garth autentiserings- eller API-feil under henting av søvndata: {str(e)}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"En uventet feil oppstod under henting av søvndata med garth: {str(e)}", exc_info=True)
            return []

    async def get_heart_rate_data(self, date: datetime) -> List[Dict[str, Any]]:
        """Hent pulsdata for én gitt dato ved hjelp av garth.connectapi."""
        date_str = date.strftime("%Y-%m-%d")
        logger.info(f"Henter pulsdata for {date_str} med garth.connectapi")
        try:
            await self._wait_for_rate_limit()
            
            heart_rate_response_list = await asyncio.to_thread(
                garth.connectapi,
                "/wellness-service/wellness/dailyHeartRate",
                params={"date": date_str}
            )
            
            if isinstance(heart_rate_response_list, list):
                logger.info(f"Hentet {len(heart_rate_response_list)} pulsdatapunkter for {date_str}.")
                return heart_rate_response_list
            elif heart_rate_response_list is None:
                logger.warning(f"Mottok ingen pulsdata (None) for {date_str} fra garth.connectapi.")
                return []
            else:
                logger.warning(f"Uventet format på pulsdata mottatt for {date_str}: {type(heart_rate_response_list)}")
                return []

        except GarthException as e:
            logger.error(f"Garth autentiserings- eller API-feil under henting av pulsdata for {date_str}: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"En uventet feil oppstod under henting av pulsdata for {date_str}: {e}", exc_info=True)
            return []

    async def get_resting_heart_rate_data(self, date: datetime) -> List[Dict[str, Any]]:
        """Hent hvilepuls (RHR) for én gitt dato ved hjelp av garth.connectapi."""
        date_str = date.strftime("%Y-%m-%d")
        logger.info(f"Henter statistikk (inkl. hvilepuls) for {date_str} med garth.connectapi")
        try:
            await self._wait_for_rate_limit()

            stats_response_dict = await asyncio.to_thread(
                garth.connectapi,
                "/wellness-service/wellness/dailySummary",
                params={"date": date_str}
            )

            if isinstance(stats_response_dict, dict):
                if 'restingHeartRate' not in stats_response_dict:
                    logger.warning(f"'restingHeartRate' mangler i dailySummary respons for {date_str}")
                
                rhr_data = {
                    'date': date_str,
                    'resting_heart_rate': stats_response_dict.get('restingHeartRate'),
                    'max_heart_rate': stats_response_dict.get('maxHeartRate'),
                    'min_heart_rate': stats_response_dict.get('minHeartRate')
                }
                logger.info(f"Hentet hvilepulsdata for {date_str}: RHR={rhr_data.get('resting_heart_rate')}")
                return [rhr_data]
            elif stats_response_dict is None:
                logger.warning(f"Mottok ingen statistikkdata (None) for {date_str}")
                return []
            else:
                logger.warning(f"Uventet format på statistikkdata for {date_str}: {type(stats_response_dict)}")
                return []

        except GarthException as e:
            logger.error(f"Garth autentiserings- eller API-feil under henting av hvilepulsdata for {date_str}: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"En uventet feil oppstod under henting av hvilepulsdata for {date_str}: {e}", exc_info=True)
            return []

    async def sync_historical_data(self, year: int) -> Dict[str, Any]:
        """Synkroniser historiske data for et gitt år."""
        logger.info(f"Starter synkronisering av historiske data for år {year}")
        
        all_activities = []
        all_sleep_entries = []
        
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)
        
        # Synkroniser aktiviteter
        try:
            activities = await self.get_activities(start_date, end_date)
            all_activities.extend(activities)
            logger.info(f"Hentet {len(activities)} aktiviteter for år {year}")
        except Exception as e:
            logger.error(f"Feil under synkronisering av aktiviteter for år {year}: {e}")
        
        # Synkroniser søvndata
        try:
            sleep_data = await self.get_sleep_data(start_date, end_date)
            all_sleep_entries.extend(sleep_data)
            logger.info(f"Hentet {len(sleep_data)} søvnregistreringer for år {year}")
        except Exception as e:
            logger.error(f"Feil under synkronisering av søvndata for år {year}: {e}")
        
        return {
            "year": year,
            "total_activities_synced": len(all_activities),
            "total_sleep_entries_synced": len(all_sleep_entries),
            "all_activities": all_activities,
            "all_sleep_entries": all_sleep_entries
        }

